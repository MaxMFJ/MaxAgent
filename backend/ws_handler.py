"""
主 WebSocket /ws 端点
将各消息类型分发到独立 handler 函数，保持可读性和可扩展性。
支持断线重连后任务恢复、服务端心跳保活。
"""
import asyncio
import json
import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app_state import (
    get_server_status, get_agent_core, get_autonomous_agent,
    get_llm_client, session_stream_tasks,
    get_task_tracker, AutoTaskStatus, TaskType,
    get_chat_runner,
)
from connection_manager import (
    connection_manager, safe_send_json, ClientType,
)
from auth import verify_token

from agent.system_message_service import get_system_message_service, MessageCategory
from agent.episodic_memory import get_episodic_memory, get_strategy_db, Episode
from agent.model_selector import get_model_selector
from agent.local_llm_manager import get_local_llm_manager

try:
    from core.concurrency_limiter import get_concurrency_limiter
except ImportError:
    get_concurrency_limiter = None

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # 服务端心跳间隔（秒）


# ============== Message Handlers ==============

async def _cancel_orphan_tasks(session_id: str):
    """当 session 内所有客户端都已断开时，取消该 session 的运行中任务"""
    tracker = get_task_tracker()

    # 取消 autonomous 任务
    tt = tracker.get_by_session(session_id)
    if tt and tt.status == AutoTaskStatus.RUNNING and tt.asyncio_task and not tt.asyncio_task.done():
        tt.asyncio_task.cancel()
        try:
            await tt.asyncio_task
        except asyncio.CancelledError:
            pass
        await tracker.finish(tt.task_id, AutoTaskStatus.STOPPED)
        logger.info(f"Orphan autonomous task cancelled (session: {session_id}, task: {tt.task_id})")

    # 取消 chat 流任务
    chat_tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)
    if chat_tt and chat_tt.status == AutoTaskStatus.RUNNING and chat_tt.asyncio_task and not chat_tt.asyncio_task.done():
        chat_tt.asyncio_task.cancel()
        try:
            await chat_tt.asyncio_task
        except asyncio.CancelledError:
            pass
        await tracker.finish(chat_tt.task_id, AutoTaskStatus.STOPPED)
        logger.info(f"Orphan chat task cancelled (session: {session_id}, task: {chat_tt.task_id})")

    task = session_stream_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info(f"Orphan stream task cancelled (session: {session_id})")


async def _handle_stop(message: dict, websocket: WebSocket, current_session_id: str, actual_client_id: str):
    session_id = message.get("session_id") or message.get("conversation_id") or current_session_id

    # 停止 chat 流任务
    task = session_stream_tasks.get(session_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        session_stream_tasks.pop(session_id, None)

    # 停止 autonomous 任务
    tracker = get_task_tracker()
    tt = tracker.get_by_session(session_id)
    if tt and tt.status == AutoTaskStatus.RUNNING and tt.asyncio_task and not tt.asyncio_task.done():
        tt.asyncio_task.cancel()
        try:
            await tt.asyncio_task
        except asyncio.CancelledError:
            pass
        await tracker.finish(tt.task_id, AutoTaskStatus.STOPPED)

    stopped_msg = {"type": "stopped", "session_id": session_id}
    await safe_send_json(websocket, stopped_msg)
    await connection_manager.broadcast_to_session(session_id, stopped_msg, exclude_client=actual_client_id)
    logger.info(f"Stream stopped by user (session: {session_id})")


async def _handle_chat(
    message: dict, websocket: WebSocket,
    current_session_id: str, actual_client_id: str, actual_client_type: ClientType,
):
    """处理 chat 消息：流式对话"""
    agent_core = get_agent_core()
    content = message.get("content", "")
    session_id = message.get("session_id") or message.get("conversation_id") or current_session_id

    logger.info(f"Received chat message (session: {session_id}): {content[:100]}...")

    await connection_manager.broadcast_to_session(
        session_id,
        {
            "type": "user_message",
            "content": content,
            "from_client": actual_client_id,
            "from_client_type": actual_client_type.value,
            "timestamp": datetime.now().isoformat(),
        },
        exclude_client=actual_client_id,
    )

    chat_runner = get_chat_runner()
    if not chat_runner:
        logger.error("Agent not initialized!")
        await safe_send_json(websocket, {"type": "error", "message": "Agent not initialized"})
        try:
            get_system_message_service().add_error(
                "对话不可用", "Agent 未初始化，请检查后端服务与模型配置",
                source="chat", category=MessageCategory.SYSTEM_ERROR.value,
            )
        except Exception as _e:
            logger.warning(f"Failed to push error notification: {_e}")
        return session_id

    if session_id in session_stream_tasks:
        old_task = session_stream_tasks[session_id]
        if not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass
        session_stream_tasks.pop(session_id, None)

    _sid = session_id
    _cid = actual_client_id
    _content = content

    async def _run_stream_and_send():
        """
        Chat 流任务：所有 chunk 同时写入 TaskTracker 缓冲。
        客户端断线后任务继续执行，重连后可通过 resume_chat 恢复。
        """
        tracker = get_task_tracker()
        chat_task_id = f"chat_{_sid}_{uuid.uuid4().hex[:6]}"

        bg_task_ref = session_stream_tasks.get(_sid)
        await tracker.register(
            chat_task_id, _sid, _content[:200],
            asyncio_task=bg_task_ref,
            task_type=TaskType.CHAT,
        )

        chunk_count = 0
        has_error = False
        client_gone = False
        total_usage = None
        extra_system_prompt = ""
        final_status = AutoTaskStatus.COMPLETED

        try:
            try:
                from agent.web_augmented_thinking import ThinkingAugmenter
                aug = ThinkingAugmenter()
                a = await aug.augment(_content)
                if a and a.get("success"):
                    extra_system_prompt = aug.format_augmentation_for_llm(a)
                    if extra_system_prompt:
                        web_chunk = {"type": "web_augmentation", "augmentation_type": a.get("type"), "query": a.get("query"), "success": True}
                        tracker.record_chunk(chat_task_id, web_chunk)
                        if not client_gone:
                            if not await safe_send_json(websocket, web_chunk):
                                client_gone = True
                        if not client_gone:
                            await connection_manager.broadcast_to_session(_sid, web_chunk, exclude_client=_cid)
            except Exception as e:
                logger.warning(f"Web augmentation failed: {e}")

            async for chunk in chat_runner.run_stream(_content, session_id=_sid, extra_system_prompt=extra_system_prompt):
                chunk_count += 1
                chunk_type = chunk.get("type", "unknown")
                if chunk_type == "stream_end":
                    total_usage = chunk.get("usage")
                    continue
                if chunk_type == "tool_result":
                    data = chunk.pop("data", None)
                    to_send = {k: v for k, v in chunk.items()}
                    tracker.record_chunk(chat_task_id, to_send)
                    if not client_gone:
                        if not await safe_send_json(websocket, to_send):
                            client_gone = True
                            logger.info(f"Chat stream: client gone during tool_result, task continues in background (task_id={chat_task_id})")
                    if not client_gone:
                        await connection_manager.broadcast_to_session(_sid, to_send, exclude_client=_cid)
                    if data and not client_gone:
                        from agent.image_extractor import extract_image_from_result
                        img = extract_image_from_result(data)
                        if img:
                            tracker.record_chunk(chat_task_id, img)
                            if not await safe_send_json(websocket, img):
                                client_gone = True
                            if not client_gone:
                                await connection_manager.broadcast_to_session(_sid, img, exclude_client=_cid)
                else:
                    # 保证 error 类 chunk 同时带 message 与 error，方便 Mac App 等客户端解析
                    if chunk_type == "error":
                        err_text = chunk.get("error") or chunk.get("message") or "未知错误"
                        chunk = {"type": "error", "error": err_text, "message": err_text}
                    tracker.record_chunk(chat_task_id, chunk)
                    if not client_gone:
                        if not await safe_send_json(websocket, chunk):
                            client_gone = True
                            logger.info(f"Chat stream: client gone, task continues in background (task_id={chat_task_id})")
                    if not client_gone:
                        await connection_manager.broadcast_to_session(_sid, chunk, exclude_client=_cid)
                if chunk_type == "error":
                    has_error = True
                    err_msg = chunk.get("error") or chunk.get("message") or "未知错误"
                    try:
                        get_system_message_service().add_error(
                            "对话执行错误", err_msg,
                            source="chat_stream", category=MessageCategory.SYSTEM_ERROR.value,
                        )
                    except Exception as _e:
                        logger.warning(f"Failed to push error notification: {_e}")

            if not has_error:
                _ac = get_agent_core()
                model_name = _ac.llm.config.model if _ac and _ac.llm else None
                done_msg = {"type": "done", "model": model_name}
                if total_usage:
                    done_msg["usage"] = total_usage
                tracker.record_chunk(chat_task_id, done_msg)
                if not client_gone:
                    await safe_send_json(websocket, done_msg)
                    await connection_manager.broadcast_to_session(_sid, done_msg, exclude_client=_cid)
                else:
                    await connection_manager.broadcast_to_session(_sid, done_msg)

        except asyncio.CancelledError:
            final_status = AutoTaskStatus.STOPPED
            stopped_msg = {"type": "stopped", "session_id": _sid}
            tracker.record_chunk(chat_task_id, stopped_msg)
            await safe_send_json(websocket, stopped_msg)
            await connection_manager.broadcast_to_session(_sid, stopped_msg, exclude_client=_cid)
            raise
        except WebSocketDisconnect:
            logger.info(f"Chat stream: WebSocket disconnected, task continues in background (task_id={chat_task_id})")
        except Exception as e:
            final_status = AutoTaskStatus.ERROR
            logger.error(f"Error in stream: {e}", exc_info=True)
            err_msg = str(e)
            err_chunk = {"type": "error", "message": err_msg, "error": err_msg}
            tracker.record_chunk(chat_task_id, err_chunk)
            if not client_gone:
                await safe_send_json(websocket, err_chunk)
            try:
                get_system_message_service().add_error(
                    "对话执行错误", str(e),
                    source="chat_stream", category=MessageCategory.SYSTEM_ERROR.value,
                )
            except Exception as _e:
                logger.warning(f"Failed to push error notification: {_e}")
        finally:
            await tracker.finish(chat_task_id, final_status)
            session_stream_tasks.pop(_sid, None)

    session_stream_tasks[_sid] = asyncio.create_task(_run_stream_and_send())
    return session_id


async def _handle_new_session(message: dict, websocket: WebSocket, current_session_id: str, actual_client_id: str):
    session_id = message.get("session_id", f"session_{id(websocket)}")
    old_session_id = current_session_id

    async with connection_manager._lock:
        if actual_client_id in connection_manager._connections:
            connection_manager._connections[actual_client_id].session_id = session_id
            if old_session_id in connection_manager._session_connections:
                connection_manager._session_connections[old_session_id].discard(actual_client_id)
            if session_id not in connection_manager._session_connections:
                connection_manager._session_connections[session_id] = set()
            connection_manager._session_connections[session_id].add(actual_client_id)

    logger.info(f"New session created: {session_id}")
    await safe_send_json(websocket, {
        "type": "session_created",
        "session_id": session_id,
        "clients_in_session": connection_manager.get_session_clients(session_id),
    })
    return session_id


async def _handle_clear_session(message: dict, websocket: WebSocket, current_session_id: str, actual_client_id: str):
    agent_core = get_agent_core()
    session_id = message.get("session_id") or current_session_id
    if agent_core:
        agent_core.reset_conversation(session_id)
        logger.info(f"Session cleared: {session_id}")
    await safe_send_json(websocket, {"type": "session_cleared", "session_id": session_id})
    await connection_manager.broadcast_to_session(
        session_id,
        {"type": "session_cleared", "session_id": session_id, "by_client": actual_client_id},
        exclude_client=actual_client_id,
    )


# ============== Autonomous Task (非阻塞 + 断线恢复) ==============

async def _autonomous_task_worker(
    task_id: str, task: str, session_id: str,
):
    """
    后台协程：执行自主任务，将输出 chunk 缓冲到 TaskTracker，
    同时广播给 session 内所有在线客户端。
    即使所有客户端断线，任务仍继续执行。
    """
    tracker = get_task_tracker()
    autonomous_agent = get_autonomous_agent()
    final_status = AutoTaskStatus.COMPLETED

    async def _run_with_limit():
        async for chunk in autonomous_agent.run_autonomous(task, session_id=session_id):
            tracker.record_chunk(task_id, chunk)
            await connection_manager.broadcast_to_session(session_id, chunk)

            chunk_type = chunk.get("type")

            if chunk_type == "error":
                err_msg = chunk.get("error") or chunk.get("message") or "未知错误"
                try:
                    get_system_message_service().add_error(
                        "自主任务执行错误",
                        f"任务: {task[:100]}\n错误: {err_msg}",
                        source="autonomous_task",
                        category=MessageCategory.SYSTEM_ERROR.value,
                    )
                except Exception as _e:
                    logger.warning(f"Failed to push error notification: {_e}")

            elif chunk_type == "task_stopped":
                nonlocal final_status
                final_status = AutoTaskStatus.STOPPED
                try:
                    reason = chunk.get("message") or chunk.get("reason") or "未知原因"
                    get_system_message_service().add_error(
                        "自主任务被停止",
                        f"任务: {task[:100]}\n原因: {reason}\n建议: {chunk.get('recommendation', '')}",
                        source="autonomous_task",
                        category=MessageCategory.SYSTEM_ERROR.value,
                    )
                except Exception as _e:
                    logger.warning(f"Failed to push stop notification: {_e}")

            elif chunk_type == "task_complete":
                try:
                    memory = get_episodic_memory()
                    episode = Episode(
                        episode_id=chunk.get("task_id", ""),
                        task_description=task,
                        result=chunk.get("summary", ""),
                        success=chunk.get("success", False),
                        total_actions=chunk.get("total_actions", 0),
                        total_iterations=chunk.get("iterations", 0),
                        token_usage=chunk.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
                    )
                    memory.add_episode(episode)
                except Exception as e:
                    logger.error(f"Failed to save episode: {e}")
                try:
                    success = chunk.get("success", False)
                    summary = chunk.get("summary", "") or task[:200]
                    total_actions = chunk.get("total_actions", 0)
                    title = "任务完成" if success else "任务未完成"
                    content = f"任务: {task[:100]}{'...' if len(task) > 100 else ''}\n总结: {summary}\n动作数: {total_actions}"
                    get_system_message_service().add_info(
                        title, content,
                        source="autonomous_task", category=MessageCategory.TASK.value,
                    )
                except Exception as e:
                    logger.warning(f"System notification for task_complete failed: {e}")

    try:
        if get_concurrency_limiter is not None:
            async with get_concurrency_limiter().autonomous_slot():
                await _run_with_limit()
        else:
            await _run_with_limit()

        done_chunk = {"type": "done"}
        tracker.record_chunk(task_id, done_chunk)
        await connection_manager.broadcast_to_session(session_id, done_chunk)

    except asyncio.CancelledError:
        final_status = AutoTaskStatus.STOPPED
        stopped_chunk = {"type": "stopped", "session_id": session_id}
        tracker.record_chunk(task_id, stopped_chunk)
        await connection_manager.broadcast_to_session(session_id, stopped_chunk)
        raise
    except Exception as e:
        final_status = AutoTaskStatus.ERROR
        logger.error(f"Error in autonomous execution: {e}", exc_info=True)
        err_chunk = {"type": "error", "message": str(e)}
        tracker.record_chunk(task_id, err_chunk)
        await connection_manager.broadcast_to_session(session_id, err_chunk)
        try:
            get_system_message_service().add_error(
                "自主任务执行错误", str(e),
                source="autonomous_task", category=MessageCategory.SYSTEM_ERROR.value,
            )
        except Exception as _e:
            logger.warning(f"Failed to push error notification: {_e}")
    finally:
        await tracker.finish(task_id, final_status)
        # 确保客户端一定能收到结束信号，避免手机端一直转圈（异常/取消时上面只发了 error/stopped，补发 done）
        try:
            await connection_manager.broadcast_to_session(session_id, {"type": "done"})
        except Exception as _e:
            logger.warning(f"Failed to broadcast done in autonomous worker finally: {_e}")


async def _handle_autonomous_task(
    message: dict, websocket: WebSocket,
    current_session_id: str, actual_client_id: str, actual_client_type: ClientType,
):
    """非阻塞启动自主任务，立即返回 task_id 给客户端"""
    autonomous_agent = get_autonomous_agent()
    task = message.get("task", "")
    session_id = message.get("session_id") or current_session_id

    # 将当前连接加入任务使用的 session，否则 broadcast_to_session(session_id, chunk) 发不到本客户端
    if session_id != current_session_id:
        async with connection_manager._lock:
            if actual_client_id in connection_manager._connections:
                conn = connection_manager._connections[actual_client_id]
                old_sid = conn.session_id
                conn.session_id = session_id
                if old_sid in connection_manager._session_connections:
                    connection_manager._session_connections[old_sid].discard(actual_client_id)
                if session_id not in connection_manager._session_connections:
                    connection_manager._session_connections[session_id] = set()
                connection_manager._session_connections[session_id].add(actual_client_id)

    enable_model_selection = message.get("enable_model_selection", True)
    prefer_local = message.get("prefer_local", False)

    if autonomous_agent:
        autonomous_agent.enable_model_selection = enable_model_selection
        autonomous_agent._prefer_local = prefer_local

    logger.info(f"Received autonomous task (session: {session_id}): {task[:100]}...")

    await connection_manager.broadcast_to_session(
        session_id,
        {
            "type": "autonomous_task_started",
            "task": task,
            "from_client": actual_client_id,
            "from_client_type": actual_client_type.value,
            "timestamp": datetime.now().isoformat(),
        },
        exclude_client=actual_client_id,
    )

    if not autonomous_agent:
        await safe_send_json(websocket, {"type": "error", "message": "Autonomous agent not initialized"})
        try:
            get_system_message_service().add_error(
                "自主任务不可用", "自主执行 Agent 未初始化，请检查后端服务",
                source="autonomous_task", category=MessageCategory.SYSTEM_ERROR.value,
            )
        except Exception as _e:
            logger.warning(f"Failed to push error notification: {_e}")
        return

    task_id = str(uuid.uuid4())[:8]
    tracker = get_task_tracker()

    bg_task = asyncio.create_task(
        _autonomous_task_worker(task_id, task, session_id)
    )
    await tracker.register(task_id, session_id, task, bg_task)

    await safe_send_json(websocket, {
        "type": "autonomous_task_accepted",
        "task_id": task_id,
        "session_id": session_id,
    })


# ============== Resume Task (断线重连恢复) ==============

async def _handle_resume_task(message: dict, websocket: WebSocket, current_session_id: str):
    """
    客户端重连后发送 resume_task，服务端回放缓冲的 chunks，
    如果任务仍在运行，后续输出会通过 session 广播自动送达。
    """
    session_id = message.get("session_id") or current_session_id
    tracker = get_task_tracker()
    tt = tracker.get_by_session(session_id)

    if not tt:
        await safe_send_json(websocket, {
            "type": "resume_result",
            "session_id": session_id,
            "found": False,
            "message": "没有找到该会话的任务记录",
        })
        return

    buffered = tracker.get_buffered_chunks(tt.task_id)

    await safe_send_json(websocket, {
        "type": "resume_result",
        "session_id": session_id,
        "found": True,
        "task_id": tt.task_id,
        "task_description": tt.task_description,
        "status": tt.status.value,
        "buffered_count": len(buffered),
    })

    for chunk in buffered:
        if not await safe_send_json(websocket, chunk):
            break

    if tt.status == AutoTaskStatus.RUNNING:
        await safe_send_json(websocket, {
            "type": "resume_streaming",
            "task_id": tt.task_id,
            "message": "任务仍在执行中，后续输出将实时推送",
        })

    logger.info(
        f"Task resumed for session {session_id}: task_id={tt.task_id}, "
        f"status={tt.status.value}, replayed={len(buffered)} chunks"
    )


async def _handle_resume_chat(message: dict, websocket: WebSocket, current_session_id: str):
    """
    客户端重连后发送 resume_chat，服务端回放 chat 流缓冲的 chunks。
    如果 chat 任务仍在运行，后续输出会通过 session 广播自动送达。
    """
    session_id = message.get("session_id") or current_session_id
    tracker = get_task_tracker()
    tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)

    if not tt:
        await safe_send_json(websocket, {
            "type": "resume_chat_result",
            "session_id": session_id,
            "found": False,
            "message": "没有找到该会话的 chat 任务记录",
        })
        return

    buffered = tracker.get_buffered_chunks(tt.task_id)

    await safe_send_json(websocket, {
        "type": "resume_chat_result",
        "session_id": session_id,
        "found": True,
        "task_id": tt.task_id,
        "status": tt.status.value,
        "buffered_count": len(buffered),
    })

    for chunk in buffered:
        if not await safe_send_json(websocket, chunk):
            break

    if tt.status == AutoTaskStatus.RUNNING:
        await safe_send_json(websocket, {
            "type": "resume_chat_streaming",
            "task_id": tt.task_id,
            "message": "Chat 任务仍在执行中，后续输出将实时推送",
        })

    logger.info(
        f"Chat resumed for session {session_id}: task_id={tt.task_id}, "
        f"status={tt.status.value}, replayed={len(buffered)} chunks"
    )


# ============== Query Handlers ==============

async def _handle_get_episodes(message: dict, websocket: WebSocket):
    try:
        memory = get_episodic_memory()
        episodes = memory.get_recent(count=message.get("count", 10))
        await safe_send_json(websocket, {
            "type": "episodes",
            "episodes": [ep.to_dict() for ep in episodes],
        })
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_get_statistics(message: dict, websocket: WebSocket):
    try:
        memory = get_episodic_memory()
        stats = memory.get_statistics()
        strategies = get_strategy_db().get_top_strategies(5)
        await safe_send_json(websocket, {
            "type": "statistics",
            "stats": stats,
            "top_strategies": strategies,
        })
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_get_system_messages(message: dict, websocket: WebSocket):
    try:
        svc = get_system_message_service()
        limit = message.get("limit", 50)
        cat = message.get("category")
        await safe_send_json(websocket, {
            "type": "system_messages",
            "messages": svc.get_all(limit=limit, category=cat),
            "unread_count": svc.get_unread_count(),
        })
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_mark_system_message_read(message: dict, websocket: WebSocket):
    try:
        svc = get_system_message_service()
        msg_id = message.get("message_id", "")
        svc.mark_read(msg_id)
        await safe_send_json(websocket, {
            "type": "system_message_read",
            "message_id": msg_id,
            "unread_count": svc.get_unread_count(),
        })
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_mark_all_system_messages_read(message: dict, websocket: WebSocket):
    try:
        svc = get_system_message_service()
        count = svc.mark_all_read()
        await safe_send_json(websocket, {
            "type": "system_messages_all_read",
            "marked": count,
            "unread_count": 0,
        })
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_get_model_stats(message: dict, websocket: WebSocket):
    try:
        selector = get_model_selector()
        stats = selector.get_statistics()
        await safe_send_json(websocket, {"type": "model_stats", "stats": stats})
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


async def _handle_analyze_task(message: dict, websocket: WebSocket):
    try:
        task_content = message.get("task", "")
        selector = get_model_selector()
        manager = get_local_llm_manager()
        _, local_config = await manager.get_client(force_refresh=True)

        from agent.local_llm_manager import LocalLLMProvider
        local_available = local_config.provider != LocalLLMProvider.NONE

        selection = selector.select(
            task=task_content,
            local_available=local_available,
            remote_available=get_llm_client() is not None,
        )
        await safe_send_json(websocket, {"type": "task_analysis", "selection": selection.to_dict()})
    except Exception as e:
        await safe_send_json(websocket, {"type": "error", "message": str(e)})


# ============== Server-side Heartbeat ==============

async def _heartbeat_loop(websocket: WebSocket, client_id: str):
    """服务端定时发送心跳，检测连接是否存活"""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if not await safe_send_json(websocket, {
                "type": "server_ping",
                "timestamp": datetime.now().isoformat(),
            }):
                logger.info(f"Heartbeat failed for {client_id}, connection likely dead")
                break
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


# ============== Main WebSocket Endpoint ==============

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    client_type: Optional[str] = Query("unknown"),
    client_id: Optional[str] = Query(None),
):
    """WebSocket endpoint for streaming chat with multi-client support"""
    if not verify_token(token):
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    actual_client_id = client_id or f"client_{secrets.token_hex(8)}"
    actual_client_type = ClientType(client_type) if client_type in [e.value for e in ClientType] else ClientType.UNKNOWN

    current_session_id = "default"
    conn = await connection_manager.connect(
        websocket=websocket,
        client_id=actual_client_id,
        client_type=actual_client_type,
        session_id=current_session_id,
    )

    logger.info(f"WebSocket connection established: {actual_client_id} ({actual_client_type.value})")

    # 检查该 session 是否有正在运行的任务
    tracker = get_task_tracker()
    running_task = tracker.get_by_session(current_session_id)
    has_running_task = running_task and running_task.status == AutoTaskStatus.RUNNING

    running_chat = tracker.get_by_session(current_session_id, task_type=TaskType.CHAT)
    has_running_chat = running_chat and running_chat.status == AutoTaskStatus.RUNNING

    unread_count = 0
    try:
        unread_count = get_system_message_service().get_unread_count()
    except Exception:
        pass
    await safe_send_json(websocket, {
        "type": "connected",
        "client_id": actual_client_id,
        "session_id": current_session_id,
        "clients_in_session": connection_manager.get_session_clients(current_session_id),
        "server_status": get_server_status().value,
        "unread_system_messages": unread_count,
        "has_running_task": has_running_task,
        "running_task_id": running_task.task_id if has_running_task else None,
        "has_running_chat": has_running_chat,
        "running_chat_task_id": running_chat.task_id if has_running_chat else None,
    })

    if unread_count > 0:
        try:
            svc = get_system_message_service()
            for msg_dict in svc.get_all(limit=50):
                if not msg_dict.get("read", False):
                    await safe_send_json(websocket, {
                        "type": "system_notification",
                        "notification": msg_dict,
                        "unread_count": unread_count,
                    })
        except Exception as e:
            logger.warning(f"Failed to push system messages on connect: {e}")

    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, actual_client_id))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            conn.last_activity = datetime.now()

            msg_type = message.get("type")

            if msg_type == "stop":
                await _handle_stop(message, websocket, current_session_id, actual_client_id)

            elif msg_type == "chat":
                new_sid = await _handle_chat(message, websocket, current_session_id, actual_client_id, actual_client_type)
                if new_sid:
                    current_session_id = new_sid

            elif msg_type == "ping":
                await safe_send_json(websocket, {"type": "pong"})

            elif msg_type == "pong":
                pass

            elif msg_type == "new_session":
                current_session_id = await _handle_new_session(message, websocket, current_session_id, actual_client_id)

            elif msg_type == "clear_session":
                await _handle_clear_session(message, websocket, current_session_id, actual_client_id)

            elif msg_type == "autonomous_task":
                await _handle_autonomous_task(message, websocket, current_session_id, actual_client_id, actual_client_type)

            elif msg_type == "resume_task":
                await _handle_resume_task(message, websocket, current_session_id)

            elif msg_type == "resume_chat":
                await _handle_resume_chat(message, websocket, current_session_id)

            elif msg_type == "get_episodes":
                await _handle_get_episodes(message, websocket)

            elif msg_type == "get_statistics":
                await _handle_get_statistics(message, websocket)

            elif msg_type == "get_system_messages":
                await _handle_get_system_messages(message, websocket)

            elif msg_type == "mark_system_message_read":
                await _handle_mark_system_message_read(message, websocket)

            elif msg_type == "mark_all_system_messages_read":
                await _handle_mark_all_system_messages_read(message, websocket)

            elif msg_type == "get_model_stats":
                await _handle_get_model_stats(message, websocket)

            elif msg_type == "analyze_task":
                await _handle_analyze_task(message, websocket)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {actual_client_id}")
        await connection_manager.broadcast_to_session(
            current_session_id,
            {
                "type": "client_disconnected",
                "client_id": actual_client_id,
                "client_type": actual_client_type.value,
            },
            exclude_client=actual_client_id,
        )
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await safe_send_json(websocket, {"type": "error", "message": str(e)})
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        await connection_manager.disconnect(actual_client_id)

        remaining = connection_manager.get_session_client_count(current_session_id)
        if remaining == 0:
            await _cancel_orphan_tasks(current_session_id)
