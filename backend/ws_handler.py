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
    get_chat_runner, AUTO_DELEGATE_WHEN_MAIN_BUSY,
)
from task_persistence import get_persistence_manager, PersistentTaskStatus
from connection_manager import (
    connection_manager, safe_send_json, ClientType,
    remove_ws_write_lock,
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
try:
    from core.timeout_policy import get_timeout_policy
except ImportError:
    get_timeout_policy = None

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # 服务端心跳间隔（秒）

# ─── chat_to_duck 直聊回调映射 ──────────────────────────────────────────────
# task_id → WebSocket  （主 Backend 将 Duck 结果路由给请求发起方）
_duck_direct_chat_callbacks: dict[str, WebSocket] = {}


# ─── Duck 完成自动续步钩子 ───────────────────────────────────────────────────

async def _run_agent_and_broadcast_result(
    session_id: str,
    prompt: str,
    chat_runner,
    task_id: str,
    label: str = "Duck",
) -> None:
    """
    运行主 Agent（带工具执行能力），收集完整响应后作为 duck_task_complete 广播。
    解决：run_stream 产生的 chunk 消息在客户端空闲 WS 循环中无法被处理的问题。
    agent 可在此过程中使用 write_file / terminal 等工具实际执行任务。
    同时向监控面板广播 monitor_event，使主 Agent 执行过程可见。
    """
    # 生成一个钩子内任务 ID，用于监控面板追踪
    hook_task_id = f"duck_hook_{task_id}_{uuid.uuid4().hex[:6]}"

    # 广播任务开始事件到监控面板
    await broadcast_monitor_event(
        session_id, hook_task_id,
        {"type": "task_start", "task": prompt[:120], "timestamp": datetime.now().isoformat()},
        task_type="chat",
        worker_type="main",
        worker_id="main",
    )

    try:
        full_text = ""
        tool_calls_used: list[str] = []

        async for chunk in chat_runner.run_stream(prompt, session_id=session_id):
            ctype = chunk.get("type", "")
            if ctype == "chunk":
                full_text += chunk.get("content", "")
            elif ctype == "tool_call":
                tool_calls_used.append(chunk.get("tool_name", chunk.get("action_type", "")))
            elif ctype in ("stream_end", "error"):
                if ctype == "error":
                    full_text += f"\n\n[错误：{chunk.get('error', '')}]"

            # ── 向监控面板广播执行过程 ──────────────────────────────────────
            if ctype in ("llm_request_start", "llm_request_end", "tool_call", "tool_result",
                         "thinking", "chunk", "error"):
                await broadcast_monitor_event(
                    session_id, hook_task_id, chunk,
                    task_type="chat",
                    worker_type="main",
                    worker_id="main",
                )

        # 广播任务完成事件到监控面板
        await broadcast_monitor_event(
            session_id, hook_task_id,
            {"type": "task_complete", "status": "completed", "timestamp": datetime.now().isoformat()},
            task_type="chat",
            worker_type="main",
            worker_id="main",
        )

        # 生成广播内容
        if not full_text.strip():
            full_text = f"{label} 任务处理完成。"
        if tool_calls_used:
            tools_note = "（使用了工具：" + "、".join(dict.fromkeys(tool_calls_used)) + "）"
            summary_content = f"{full_text}\n\n{tools_note}"
        else:
            summary_content = full_text

        # 作为 duck_task_complete 发送（Mac 客户端在 idle 状态时能正确接收）
        await connection_manager.broadcast_to_session(session_id, {
            "type": "duck_task_complete",
            "task_id": task_id,
            "success": True,
            "content": summary_content,
            "session_id": session_id,
            "duck_id": label,
        })

        # 写入对话上下文（确保即使客户端未即时收到广播，刷新后仍可看到结果）
        try:
            from agent.context_manager import context_manager as ctx_mgr_mod
            ctx = ctx_mgr_mod.get_or_create(session_id)
            ctx.add_message("assistant", summary_content)
            ctx_mgr_mod.save_session(session_id)
        except Exception as _ctx_err:
            logger.debug(f"[duck_hook] Failed to save to context: {_ctx_err}")

        logger.info(
            f"[duck_hook] Broadcast final response for session {session_id} "
            f"task {task_id} ({len(full_text)} chars, tools={tool_calls_used})"
        )
    except Exception as e:
        logger.warning(f"[duck_hook] _run_agent_and_broadcast_result failed for {session_id}: {e}")
        await broadcast_monitor_event(
            session_id, hook_task_id,
            {"type": "error", "error": str(e), "timestamp": datetime.now().isoformat()},
            task_type="chat",
            worker_type="main",
            worker_id="main",
        )


async def _on_duck_task_complete(session_id: str, task) -> None:
    """
    Duck 子任务完成后的自动续步钩子。
    主 Agent 根据上下文判断是否需要继续后续工作（如：设计师完成后交给 coder）。
    条件：仅在 Duck 成功且主 Agent 当前不忙时触发。
    注意：自主模式（_handle_delegate_duck）的任务有 callback，scheduler 层已跳过
          _notify_session_duck_complete，故本钩子不会被自主模式触发。
    """
    from services.duck_protocol import TaskStatus

    chat_runner = get_chat_runner()
    if not chat_runner:
        return  # Agent 未初始化

    # 若主 Agent 正在忙于该 session 的其他任务，不插队
    if is_main_agent_busy(session_id, "chat"):
        return

    duck_name = getattr(task, "assigned_duck_id", "Duck") or "Duck"
    # 优先显示原始任务描述（而非 retry 增强描述）
    original_desc = getattr(task, "original_description", None) or getattr(task, "description", "") or ""
    desc_preview = original_desc[:80]

    # ── 任务失败：通知主 Agent 亲自处理 ──────────────────────────────────────
    if task.status == TaskStatus.FAILED:
        error_msg = str(task.error or "未知错误")
        try:
            from agent.context_manager import context_manager as ctx_mgr_mod
            ctx = ctx_mgr_mod.get_or_create(session_id)
            workspace_hint = ctx.get_duck_workspace_hint()

            failure_msg = (
                f"[系统通知] Duck 子任务执行失败\n"
                f"失败的 Duck：{duck_name}\n"
                f"任务描述：{desc_preview}\n"
                f"失败原因：{error_msg[:400]}\n"
            )
            if workspace_hint:
                failure_msg += f"\n{workspace_hint}\n"
            failure_msg += (
                "\n⚡ **你现在必须亲自处理此任务**（Duck 已多次尝试失败）：\n"
                "1. 如果是创建 HTML/代码/文档文件：**直接用 `write_file` 工具写入文件**，"
                "不要再委派 Duck。HTML 文件可以用纯 `write_file` 创建，不需要任何库。\n"
                "2. 如果需要运行脚本：用 `terminal` 直接执行 Python/Shell 命令。\n"
                "3. 完成后向用户汇报实际文件路径。\n"
                "⚠️ 禁止再次 delegate_duck 相同内容，必须用 write_file 或 terminal 完成。"
            )

            # 运行主 Agent（带工具执行），完成后广播最终响应给客户端
            await _run_agent_and_broadcast_result(
                session_id, failure_msg, chat_runner, task.task_id, label=duck_name
            )
        except Exception as e:
            logger.warning(f"[duck_complete_hook] Failure notification failed for session {session_id}: {e}")
        return

    # ── 任务成功：自动续步 ───────────────────────────────────────────────────
    if task.status != TaskStatus.COMPLETED:
        return  # CANCELLED 等状态不处理

    try:
        # 从工作区获取所有 Duck 任务的产出（含当前已完成的）
        from agent.context_manager import context_manager as ctx_mgr_mod
        ctx = ctx_mgr_mod.get_or_create(session_id)
        workspace_hint = ctx.get_duck_workspace_hint()

        # 从输出中获取文件路径（方便后续步骤引用）
        from services.duck_task_scheduler import get_task_scheduler
        scheduler = get_task_scheduler()
        file_paths = scheduler._extract_file_paths_from_output(task.output) if hasattr(scheduler, "_extract_file_paths_from_output") else []
        paths_hint = ""
        if file_paths:
            paths_hint = "\n本次产出文件：" + ", ".join(f"`{p}`" for p in file_paths[:5])

        # 检查是否有配套的设计规格文件（Designer Duck 会同时生成 _design_spec.md）
        import os
        design_spec_content = ""
        for fp in file_paths:
            spec_path = os.path.splitext(fp)[0] + "_design_spec.md"
            if os.path.exists(spec_path):
                try:
                    with open(spec_path, "r", encoding="utf-8") as f:
                        design_spec_content = f.read()[:2000]
                    paths_hint += f"\n设计规格文件：`{spec_path}`"
                except Exception:
                    pass
            # 也检查同目录下的 _design_spec.md
            dir_spec = os.path.join(os.path.dirname(fp), "_design_spec.md")
            if os.path.exists(dir_spec) and not design_spec_content:
                try:
                    with open(dir_spec, "r", encoding="utf-8") as f:
                        design_spec_content = f.read()[:2000]
                    paths_hint += f"\n设计规格文件：`{dir_spec}`"
                except Exception:
                    pass

        # 额外检查：Designer Duck 可能直接输出了 .md 设计文档（非 _design_spec.md 命名）
        md_files = [fp for fp in file_paths if fp.lower().endswith(".md")]
        if md_files and not design_spec_content:
            for md_fp in md_files:
                try:
                    with open(md_fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 检查是否包含设计规格关键词
                    if any(kw in content for kw in ("色彩", "配色", "Color", "布局", "Layout", "组件", "Component", "Glassmorphism", "设计")):
                        design_spec_content = content[:2000]
                        paths_hint += f"\n设计文档：`{md_fp}`"
                        break
                except Exception:
                    pass

        # 从 Duck 输出文本中提取设计规格路径（Duck 可能写到任务指定的路径，不在 file_paths 中）
        if not design_spec_content:
            import re
            output_text = str(task.output or "")
            desc_text = original_desc
            # 从输出和描述中查找 .md 路径
            for search_text in [output_text, desc_text]:
                md_path_matches = re.findall(
                    r'(/(?:Users|tmp|home)/[^\s"\'\\,，]+\.md)',
                    search_text, re.IGNORECASE,
                )
                for md_path in md_path_matches:
                    expanded = os.path.expanduser(md_path.replace("~", os.path.expanduser("~")))
                    if os.path.exists(expanded) and not design_spec_content:
                        try:
                            with open(expanded, "r", encoding="utf-8") as f:
                                content = f.read()
                            if any(kw in content for kw in ("色彩", "配色", "Color", "布局", "Layout", "设计")):
                                design_spec_content = content[:2000]
                                paths_hint += f"\n设计文档：`{expanded}`"
                        except Exception:
                            pass

        output_str = str(task.output or "")

        continuation_msg = (
            f"[系统自动续步] {duck_name} 子任务已完成：{desc_preview}{paths_hint}\n"
            f"输出摘要：{output_str[:300]}{'...' if len(output_str) > 300 else ''}\n"
        )

        # 如果有设计规格内容，注入续步消息让 Coder Duck 直接使用
        if design_spec_content:
            continuation_msg += (
                f"\n📐 **设计规格（供 Coder Duck 直接使用，无需截图看设计图）：**\n"
                f"{design_spec_content}\n"
            )

        if workspace_hint:
            continuation_msg += f"\n{workspace_hint}\n"

        # 检测是否有 PNG/JPG 但缺少 _design_spec.md，给出更具体的指引
        image_files = [fp for fp in file_paths if any(fp.lower().endswith(e) for e in (".png", ".jpg", ".jpeg"))]
        if image_files and not design_spec_content:
            # Designer Duck 生成了图片但没有设计规格——委派 Coder 时必须在 description 中写明设计图路径
            img_paths_hint = ", ".join(f"`{p}`" for p in image_files[:3])
            first_img = image_files[0]
            continuation_msg += (
                f"\n⚠️ **注意**：Designer Duck 生成了设计图（{img_paths_hint}）但未发现 `_design_spec.md`。\n"
                f"委派 Coder Duck 时，**必须在 description 中**写明：\n"
                f"1. 设计图完整路径：`{first_img}`\n"
                f"2. 明确要求：使用 call_tool(vision, action=analyze_local_image, file_path=\"{first_img}\") 直接读取设计图，"
                "**禁止**用 open+截图 或 screenshot 看设计。\n"
                "这样 Coder Duck 会直接读取图片文件进行分析，无需截图。\n"
            )

        # Duck 上下文注入：若有设计产出（Designer→Coder 串行），提供可直接复制的 delegate description
        suggested_delegate_desc = ""
        if duck_name and "designer" in duck_name.lower() and (design_spec_content or image_files):
            parts = []
            if image_files:
                _first_img = image_files[0]
                parts.append(f"设计图路径：{_first_img}")
                parts.append(f"必须用 call_tool(vision, action=analyze_local_image, file_path=\"{_first_img}\") 读取，禁止截图。")
            if design_spec_content:
                spec_preview = design_spec_content[:1500] + ("..." if len(design_spec_content) > 1500 else "")
                parts.append(f"设计规格：\n{spec_preview}")
            parts.append("任务：根据上述设计完成 HTML/CSS 实现，输出到工作区。")
            suggested_delegate_desc = "\n".join(parts)

        if suggested_delegate_desc:
            continuation_msg += (
                "\n\n📋 **【可直接使用的 delegate_duck description】**\n"
                "若需委派 Coder Duck，请将以下整段复制到 delegate_duck 的 description 参数中：\n"
                "```\n" + suggested_delegate_desc + "\n```\n"
            )

        continuation_msg += (
            "\n请根据上述工作区产出和对话上下文判断：\n"
            "1. 若还有待执行的下一步任务（如把设计图交给 coder Duck 制作 HTML），"
            "请**立即调用 delegate_duck** 并在 description 中：\n"
            "   - 明确引用相关文件的完整路径\n"
            "   - 如果有设计规格内容，必须将完整的设计规格（配色、布局、组件等）附在 description 中，"
            "这样 Coder Duck 无需截图即可直接实现\n"
            "2. 若所有步骤均已完成，向用户汇报最终产出（列出所有文件路径）。\n"
            "⚠️ 在 delegate_duck 的 description 中，必须明确写出需要参考的文件完整路径，"
            "不能只说「参考设计图」，要说「参考 /Users/xxx/Desktop/xxx.png」。"
        )

        # 运行主 Agent（带工具执行），完成后广播最终响应给客户端
        await _run_agent_and_broadcast_result(
            session_id, continuation_msg, chat_runner, task.task_id, label=duck_name
        )
    except Exception as e:
        logger.warning(f"[duck_complete_hook] Auto-resume failed for session {session_id}: {e}")


# ─── 注册钩子（模块加载时执行）────────────────────────────────────────────────
def _register_duck_hooks():
    try:
        from services.duck_task_scheduler import register_duck_complete_hook
        register_duck_complete_hook(_on_duck_task_complete)
        logger.info("Registered duck_complete auto-resume hook")
    except Exception as e:
        logger.warning(f"Failed to register duck_complete hook: {e}")

_register_duck_hooks()


# ============== Busy Check Helper ==============

def is_main_agent_busy(session_id: str, task_type: Optional[str] = None) -> bool:
    """
    判断主 Agent 当前是否正在执行该 session 的任务。

    task_type:
        "chat"       — 仅检查 chat 流任务
        "autonomous" — 仅检查 autonomous 任务
        None         — 两者均检查（任一忙即返回 True）
    """
    tracker = get_task_tracker()

    if task_type in (None, "chat"):
        stream_task = session_stream_tasks.get(session_id)
        if stream_task and not stream_task.done():
            return True
        chat_tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)
        if chat_tt and chat_tt.status == AutoTaskStatus.RUNNING:
            return True

    if task_type in (None, "autonomous"):
        auto_tt = tracker.get_by_session(session_id, task_type=TaskType.AUTONOMOUS)
        if auto_tt and auto_tt.status == AutoTaskStatus.RUNNING:
            return True

    return False


async def _try_auto_delegate(
    description: str,
    session_id: str,
    websocket: WebSocket,
    notify_type: str,
    file_paths: list | None = None,
) -> bool:
    """
    若 AUTO_DELEGATE_WHEN_MAIN_BUSY 已开启且有空闲 Duck，
    将任务自动委派给 Duck 并通知前端。

    返回 True 表示已成功委派（调用方应跳过主 Agent 执行）；
    返回 False 表示无法委派（调用方继续走原有逻辑）。
    """
    if not AUTO_DELEGATE_WHEN_MAIN_BUSY:
        return False
    try:
        from services.duck_registry import DuckRegistry
        from services.duck_task_scheduler import get_task_scheduler, ScheduleStrategy
        registry = DuckRegistry.get_instance()
        await registry.initialize()
        available = await registry.list_available()
        if not available:
            logger.info(
                f"AUTO_DELEGATE: main busy but no available Duck for session={session_id}, "
                "falling back to cancelling current task"
            )
            return False
        scheduler = get_task_scheduler()
        params = {"file_paths": file_paths} if file_paths else {}
        duck_task = await scheduler.submit(
            description=description,
            task_type="general",
            params=params,
            strategy=ScheduleStrategy.SINGLE,
            source_session_id=session_id,
        )
        logger.info(
            f"AUTO_DELEGATE: new {notify_type} task auto-delegated to Duck "
            f"(duck_task_id={duck_task.task_id}, session={session_id})"
        )
        await safe_send_json(websocket, {
            "type": "auto_delegated_to_duck",
            "notify_type": notify_type,
            "duck_task_id": duck_task.task_id,
            "session_id": session_id,
            "message": "主 Agent 正忙，任务已自动转交给分身 Duck 执行",
            "auto_delegated": True,
        })
        return True
    except Exception as e:
        logger.warning(f"AUTO_DELEGATE: failed to delegate, falling back: {e}")
        return False




async def broadcast_monitor_event(
    session_id: str,
    task_id: str,
    event: dict,
    task_type: str = "chat",
    worker_type: str = "main",
    worker_id: str = "main",
):
    """
    广播监控事件给所有客户端（用于全局监控面板）。

    Args:
        session_id: 会话 ID
        task_id: 任务 ID
        event: 事件数据 (包含 type 字段)
        task_type: 任务类型 ("chat" / "autonomous" / "duck")
        worker_type: 执行者类型 ("main" / "local_duck" / "remote_duck")
        worker_id: 执行者 ID ("main" 或 duck_id)
    """
    # 向 inner event 注入执行者信息，前端通过 event["_worker_type"] 等字段展示"谁在做"
    enriched_event = dict(event)
    enriched_event["_worker_type"] = worker_type
    enriched_event["_worker_id"] = worker_id
    enriched_event["task_type"] = task_type  # 注入 task_type，让前端 applyMonitorEvent 能识别 duck task
    if worker_type == "main":
        enriched_event["_worker_label"] = "主Agent"
    elif worker_type in ("local_duck", "remote_duck"):
        enriched_event["_worker_label"] = f"Duck[{worker_id}]"
    else:
        enriched_event["_worker_label"] = worker_id

    monitor_event = {
        "type": "monitor_event",
        "source_session": session_id,
        "task_id": task_id,
        "task_type": task_type,
        "worker_type": worker_type,
        "worker_id": worker_id,
        "event": enriched_event,
    }
    event_type = event.get("type", "unknown")
    logger.debug(
        f"Broadcasting monitor_event: type={event_type}, task_id={task_id}, "
        f"task_type={task_type}, worker={worker_type}:{worker_id}"
    )
    await connection_manager.broadcast_all(monitor_event)


# ============== Message Handlers ==============

async def _handle_client_disconnect(session_id: str):
    """
    客户端断开连接时的处理逻辑。
    不立即取消任务，而是标记为暂停状态并启动超时计时器。
    任务会继续后台执行，只有超时后才会被取消。
    """
    persistence = get_persistence_manager()
    tracker = get_task_tracker()
    
    # 标记客户端断开，启动孤儿任务超时计时器
    await persistence.mark_client_disconnected(session_id)
    
    # autonomous 任务继续后台执行，不取消
    tt = tracker.get_by_session(session_id)
    if tt and tt.status == AutoTaskStatus.RUNNING:
        logger.info(f"Client disconnected, autonomous task continues in background (session: {session_id}, task: {tt.task_id})")
    
    # chat 任务继续后台执行，不取消
    chat_tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)
    if chat_tt and chat_tt.status == AutoTaskStatus.RUNNING:
        logger.info(f"Client disconnected, chat task continues in background (session: {session_id}, task: {chat_tt.task_id})")


async def _cancel_orphan_tasks(session_id: str):
    """
    强制取消孤儿任务（仅在超时或显式调用时使用）。
    正常断开连接应使用 _handle_client_disconnect。
    """
    tracker = get_task_tracker()
    persistence = get_persistence_manager()

    # 取消 autonomous 任务
    tt = tracker.get_by_session(session_id)
    if tt and tt.status == AutoTaskStatus.RUNNING and tt.asyncio_task and not tt.asyncio_task.done():
        tt.asyncio_task.cancel()
        try:
            await tt.asyncio_task
        except asyncio.CancelledError:
            pass
        await tracker.finish(tt.task_id, AutoTaskStatus.STOPPED)
        await persistence.update_task_status(tt.task_id, PersistentTaskStatus.ORPHAN_TIMEOUT)
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
    file_paths = message.get("file_paths") or []
    session_id = message.get("session_id") or message.get("conversation_id") or current_session_id

    if file_paths:
        content = f"{content}\n\n【用户附带文件】\n" + "\n".join(f"- {p}" for p in file_paths)
        logger.info(f"Received chat message (session: {session_id}) with {len(file_paths)} file refs: {content[:100]}...")
    else:
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

    # ── 主 Agent 忙时自动委派给 Duck（缺陷修复：5.1）────────────────────────
    if is_main_agent_busy(session_id, "chat"):
        delegated = await _try_auto_delegate(content, session_id, websocket, "chat", file_paths=file_paths)
        if delegated:
            return session_id
        # 无可用 Duck：回退到旧行为（cancel 旧 chat 任务，由主 Agent 执行新任务）

    if session_id in session_stream_tasks:
        old_task = session_stream_tasks[session_id]
        if not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass
        session_stream_tasks.pop(session_id, None)

    # 防污染：新 chat 请求到达时，清空同 session 旧 chat 任务的缓冲 chunks，
    # 避免断线重连后 resume_chat 回放旧响应被误认为新请求的响应。
    tracker = get_task_tracker()
    old_chat_tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)
    if old_chat_tt:
        tracker.clear_chunks(old_chat_tt.task_id)
        logger.debug(f"Cleared old chat chunks for session {session_id} (old task: {old_chat_tt.task_id})")

    _sid = session_id
    _cid = actual_client_id
    _content = content

    async def _run_stream_and_send():
        """
        Chat 流任务：所有 chunk 同时写入 TaskTracker 缓冲。
        客户端断线后任务继续执行，重连后可通过 resume_chat 恢复。
        使用 StreamChunkDispatcher 统一分发逻辑。
        """
        from agent.stream_dispatcher import StreamChunkDispatcher

        tracker = get_task_tracker()
        chat_task_id = f"chat_{_sid}_{uuid.uuid4().hex[:6]}"

        bg_task_ref = session_stream_tasks.get(_sid)
        await tracker.register(
            chat_task_id, _sid, _content[:200],
            asyncio_task=bg_task_ref,
            task_type=TaskType.CHAT,
        )

        # 广播任务开始事件
        await broadcast_monitor_event(
            _sid, chat_task_id,
            {"type": "task_start", "task": _content[:200], "timestamp": datetime.now().isoformat()},
            task_type="chat"
        )

        dispatcher = StreamChunkDispatcher(
            task_id=chat_task_id,
            session_id=_sid,
            task_type="chat",
            tracker=tracker,
            connection_manager=connection_manager,
            websocket=websocket,
            client_id=_cid,
            safe_send_fn=safe_send_json,
            broadcast_monitor_fn=broadcast_monitor_event,
            system_message_service=get_system_message_service(),
        )

        extra_system_prompt = ""
        final_status = AutoTaskStatus.COMPLETED

        async def _on_chat_chunk(chunk: dict):
            """Chat 特有的 chunk 后处理：tool_result 的 image 提取"""
            chunk_type = chunk.get("type", "")
            if chunk_type == "tool_result":
                data = chunk.pop("data", None)
                if data and not dispatcher.client_gone:
                    from agent.image_extractor import extract_image_from_result
                    img = extract_image_from_result(data)
                    if img:
                        await dispatcher.dispatch_chunk(img)

        try:
            # Web 增强预取（Chat 特有）
            try:
                from agent.web_augmented_thinking import ThinkingAugmenter, AugmentationType
                aug = ThinkingAugmenter()
                a = await aug.augment(_content)
                if a and a.get("success"):
                    extra_system_prompt = aug.format_augmentation_for_llm(a)
                    if extra_system_prompt:
                        web_chunk = {"type": "web_augmentation", "augmentation_type": a.get("type"), "query": a.get("query"), "success": True}
                        await dispatcher.dispatch_chunk(web_chunk)
                elif a and not a.get("success"):
                    aug_type = a.get("type", "")
                    aug_query = a.get("query", "")
                    if aug_type == AugmentationType.REALTIME_INFO.value or aug_type == "realtime_info":
                        extra_system_prompt = (
                            f"\n\n[系统提示：自动联网预取 '{aug_query}' 的实时信息失败。"
                            f"但你仍然可以使用 web_search 工具获取实时数据（天气用 action=get_weather，"
                            f"新闻用 action=news，通用搜索用 action=search）。请主动调用 web_search 工具来获取用户需要的信息，"
                            f"不要直接告诉用户'找不到技能'或'无法获取'。]"
                        )
                        logger.info(f"Web augmentation failed for '{aug_query}', injected fallback hint")
            except Exception as e:
                logger.warning(f"Web augmentation failed: {e}")

            # 统一分发流
            await dispatcher.dispatch_stream(
                chat_runner.run_stream(_content, session_id=_sid, extra_system_prompt=extra_system_prompt),
                on_chunk=_on_chat_chunk,
            )

            if not dispatcher.has_error:
                _ac = get_agent_core()
                model_name = _ac.llm.config.model if _ac and _ac.llm else None
                await dispatcher.send_done(model_name=model_name)

        except asyncio.CancelledError:
            final_status = AutoTaskStatus.STOPPED
            await dispatcher.send_stopped()
            raise
        except WebSocketDisconnect:
            logger.info(f"Chat stream: WebSocket disconnected, task continues in background (task_id={chat_task_id})")
        except Exception as e:
            final_status = AutoTaskStatus.ERROR
            logger.error(f"Error in stream: {e}", exc_info=True)
            await dispatcher.send_error(str(e))
        finally:
            await dispatcher.cleanup(final_status)
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
    同时广播监控事件给所有连接的客户端（用于全局监控）。
    使用 StreamChunkDispatcher 统一分发逻辑。
    """
    from agent.stream_dispatcher import StreamChunkDispatcher

    tracker = get_task_tracker()
    autonomous_agent = get_autonomous_agent()
    final_status = AutoTaskStatus.COMPLETED

    dispatcher = StreamChunkDispatcher(
        task_id=task_id,
        session_id=session_id,
        task_type="autonomous",
        tracker=tracker,
        connection_manager=connection_manager,
        # Autonomous 模式: 无 websocket 直连，全靠 broadcast
        websocket=None,
        client_id=None,
        safe_send_fn=safe_send_json,
        broadcast_monitor_fn=broadcast_monitor_event,
        system_message_service=get_system_message_service(),
    )

    async def _on_autonomous_chunk(chunk: dict):
        """自主任务特有的 chunk 后处理逻辑"""
        chunk_type = chunk.get("type", "")

        if chunk_type == "task_stopped":
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
                    execution_time_ms=chunk.get("execution_time_ms", 0),
                    action_log=chunk.get("action_log", []),
                    token_usage=chunk.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
                )
                memory.add_episode(episode)
                # v3.8: 提取事实到持久化事实库
                try:
                    from agent.persistent_memory import FactExtractor, get_factbase
                    facts = FactExtractor.extract(
                        episode_id=episode.episode_id,
                        task_description=task,
                        action_log=chunk.get("action_log", []),
                        success=chunk.get("success", False),
                        result=chunk.get("summary", ""),
                    )
                    if facts:
                        get_factbase().add_facts(facts)
                except Exception as fact_err:
                    logger.debug(f"Fact extraction failed: {fact_err}")
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

    async def _run_with_limit():
        await dispatcher.dispatch_stream(
            autonomous_agent.run_autonomous(task, session_id=session_id),
            on_chunk=_on_autonomous_chunk,
        )

    try:
        async def _run_with_timeout():
            if get_concurrency_limiter is not None:
                async with get_concurrency_limiter().autonomous_slot():
                    await _run_with_limit()
            else:
                await _run_with_limit()

        if get_timeout_policy is not None:
            policy = get_timeout_policy()
            await asyncio.wait_for(_run_with_timeout(), timeout=policy.autonomous_timeout)
        else:
            await _run_with_timeout()

        await dispatcher.send_done()

    except asyncio.TimeoutError:
        final_status = AutoTaskStatus.ERROR
        await dispatcher.send_error("自主任务执行超时（TimeoutPolicy.autonomous_timeout）")
        try:
            get_system_message_service().add_error(
                "自主任务超时", "任务执行时间超过限制，已自动停止",
                source="autonomous_task", category=MessageCategory.SYSTEM_ERROR.value,
            )
        except Exception as _e:
            logger.warning(f"Failed to push timeout notification: {_e}")
    except asyncio.CancelledError:
        final_status = AutoTaskStatus.STOPPED
        await dispatcher.send_stopped()
        raise
    except Exception as e:
        final_status = AutoTaskStatus.ERROR
        logger.error(f"Error in autonomous execution: {e}", exc_info=True)
        await dispatcher.send_error(str(e))
        try:
            get_system_message_service().add_error(
                "自主任务执行错误", str(e),
                source="autonomous_task", category=MessageCategory.SYSTEM_ERROR.value,
            )
        except Exception as _e:
            logger.warning(f"Failed to push error notification: {_e}")
    finally:
        await dispatcher.cleanup(final_status)
        # 确保客户端一定能收到结束信号
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
    file_paths = message.get("file_paths") or []
    session_id = message.get("session_id") or current_session_id

    if file_paths:
        task = f"{task}\n\n【用户附带文件】\n" + "\n".join(f"- {p}" for p in file_paths)

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

    # ── 主 Agent 忙时自动委派给 Duck（缺陷修复：5.1）────────────────────────
    if is_main_agent_busy(session_id, "autonomous"):
        delegated = await _try_auto_delegate(task, session_id, websocket, "autonomous", file_paths=file_paths)
        if delegated:
            return
        # 无可用 Duck：回退到旧行为（TaskTracker.register 会自动 cancel 旧任务）

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
    支持从持久化检查点获取额外的任务执行历史。
    """
    session_id = message.get("session_id") or current_session_id
    tracker = get_task_tracker()
    persistence = get_persistence_manager()
    
    tt = tracker.get_by_session(session_id)
    
    # 尝试从持久化存储获取检查点
    checkpoint = await persistence.load_checkpoint_by_session(session_id)

    if not tt and not checkpoint:
        await safe_send_json(websocket, {
            "type": "resume_result",
            "session_id": session_id,
            "found": False,
            "message": "没有找到该会话的任务记录",
        })
        return

    # 优先使用内存中的任务状态
    if tt:
        buffered = tracker.get_buffered_chunks(tt.task_id)
        task_id = tt.task_id
        task_description = tt.task_description
        status = tt.status.value
    else:
        # 从持久化检查点恢复
        buffered = []
        task_id = checkpoint.task_id
        task_description = checkpoint.task_description
        status = checkpoint.status.value if hasattr(checkpoint.status, 'value') else checkpoint.status
        
        # 将检查点中的 action 历史转换为 chunks 格式
        for action_cp in checkpoint.action_checkpoints:
            buffered.append({
                "type": "action_result",
                "action_id": f"recovered_{action_cp.iteration}",
                "success": action_cp.success,
                "output": str(action_cp.output)[:500] if action_cp.output else None,
                "error": action_cp.error,
                "execution_time_ms": 0,
                "recovered_from_checkpoint": True,
            })

    await safe_send_json(websocket, {
        "type": "resume_result",
        "session_id": session_id,
        "found": True,
        "task_id": task_id,
        "task_description": task_description,
        "status": status,
        "buffered_count": len(buffered),
        "has_checkpoint": checkpoint is not None,
        "checkpoint_iteration": checkpoint.current_iteration if checkpoint else None,
    })

    for chunk in buffered:
        if not await safe_send_json(websocket, chunk):
            break

    if tt and tt.status == AutoTaskStatus.RUNNING:
        await safe_send_json(websocket, {
            "type": "resume_streaming",
            "task_id": task_id,
            "message": "任务仍在执行中，后续输出将实时推送",
        })
    elif checkpoint and checkpoint.status in [PersistentTaskStatus.RUNNING, PersistentTaskStatus.PAUSED]:
        await safe_send_json(websocket, {
            "type": "resume_streaming",
            "task_id": task_id,
            "message": "任务正在后台执行或已暂停，重连后将继续接收更新",
        })

    logger.info(
        f"Task resumed for session {session_id}: task_id={task_id}, "
        f"status={status}, replayed={len(buffered)} chunks, has_checkpoint={checkpoint is not None}"
    )


async def _handle_resume_chat(message: dict, websocket: WebSocket, current_session_id: str):
    """
    客户端重连后发送 resume_chat，服务端回放 chat 流缓冲的 chunks。
    如果 chat 任务仍在运行，后续输出会通过 session 广播自动送达。
    如果 task_tracker 没有记录（后端重启），尝试从 context_manager 恢复最后的回复。
    """
    session_id = message.get("session_id") or current_session_id
    tracker = get_task_tracker()
    tt = tracker.get_by_session(session_id, task_type=TaskType.CHAT)

    if not tt:
        # 尝试从 context_manager 恢复最后的 assistant 回复
        try:
            from agent.context_manager import context_manager
            ctx = context_manager.get_or_create(session_id)
            if ctx.recent_messages:
                # 找到最后一条 assistant 消息
                last_assistant_msg = None
                for msg in reversed(ctx.recent_messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        last_assistant_msg = msg
                        break
                
                if last_assistant_msg:
                    message_id = last_assistant_msg.get("id")
                    # 构造一个虚拟的恢复结果
                    await safe_send_json(websocket, {
                        "type": "resume_chat_result",
                        "session_id": session_id,
                        "found": True,
                        "task_id": f"recovered_{session_id}",
                        "status": "completed",
                        "buffered_count": 2,  # content + done
                        "recovered_from_context": True,
                        "is_resume": True,  # 标记为恢复性数据
                        "last_message_id": message_id,  # 客户端可用于去重
                    })
                    # 发送内容（包含 message_id + is_resume 用于客户端去重/区分）
                    await safe_send_json(websocket, {
                        "type": "content",
                        "content": last_assistant_msg["content"],
                        "message_id": message_id,
                        "is_resume": True,
                    })
                    # 发送 done
                    await safe_send_json(websocket, {
                        "type": "done",
                        "model": None,
                        "message_id": message_id,
                        "is_resume": True,
                    })
                    logger.info(f"Chat recovered from context for session {session_id}, message_id={message_id}")
                    return
        except Exception as e:
            logger.warning(f"Failed to recover chat from context: {e}")
        
        await safe_send_json(websocket, {
            "type": "resume_chat_result",
            "session_id": session_id,
            "found": False,
            "message": "没有找到该会话的 chat 任务记录",
        })
        return

    buffered = tracker.get_buffered_chunks(tt.task_id)

    # 跳过客户端断线前已成功接收的 chunk，避免重复发送
    skip_count = getattr(tt, 'client_sent_count', 0)
    chunks_to_replay = buffered[skip_count:]

    await safe_send_json(websocket, {
        "type": "resume_chat_result",
        "session_id": session_id,
        "found": True,
        "task_id": tt.task_id,
        "status": tt.status.value,
        "buffered_count": len(chunks_to_replay),
        "is_resume": True,  # 标记为恢复性回放，客户端据此区分新任务 vs 旧任务
    })

    for chunk in chunks_to_replay:
        # 为每个回放 chunk 添加 is_resume 标志，方便客户端区分
        replay_chunk = {**chunk, "is_resume": True}
        if not await safe_send_json(websocket, replay_chunk):
            break

    if tt.status == AutoTaskStatus.RUNNING:
        # 任务仍在运行，更新已发送计数（后续新 chunk 通过 broadcast 推送）
        tt.client_sent_count = len(buffered)
        await safe_send_json(websocket, {
            "type": "resume_chat_streaming",
            "task_id": tt.task_id,
            "message": "Chat 任务仍在执行中，后续输出将实时推送",
        })
    else:
        # 任务已结束，客户端已收到所有 chunk，清空缓冲防止下次重连再次重放
        tracker.clear_chunks(tt.task_id)

    logger.info(
        f"Chat resumed for session {session_id}: task_id={tt.task_id}, "
        f"status={tt.status.value}, replayed={len(chunks_to_replay)} chunks (skipped={skip_count})"
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


async def _handle_chat_to_duck(message: dict, websocket: WebSocket, current_session_id: str):
    """
    用户直聊子 Duck：向本地 Duck (内存队列) 或远程 Duck (WebSocket) 转发任务。
    结果通过 _duck_direct_chat_callbacks 路由回发起方的 WebSocket。
    """
    import uuid as _uuid
    duck_id = message.get("duck_id", "").strip()
    content = message.get("content", "").strip()
    session_id = message.get("session_id") or current_session_id

    if not duck_id or not content:
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "duck_id": duck_id,
            "error": "duck_id 和 content 均不能为空",
        })
        return

    from services.duck_registry import DuckRegistry
    from services.duck_protocol import DuckStatus, DuckMessage, DuckMessageType, DuckTaskPayload

    registry = DuckRegistry.get_instance()
    await registry.initialize()
    duck = await registry.get(duck_id)

    if not duck:
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "duck_id": duck_id,
            "error": "该 Duck 不存在",
        })
        return

    if duck.status == DuckStatus.OFFLINE:
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "duck_id": duck_id,
            "error": "该 Duck 已离线",
        })
        return

    if duck.status == DuckStatus.BUSY:
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "duck_id": duck_id,
            "error": f"该 Duck 正在执行任务（{duck.busy_reason or 'busy'}），请稍后或选择其他 Duck",
        })
        return

    task_id = f"dctask_{_uuid.uuid4().hex[:8]}"

    # 建立结果回调映射
    _duck_direct_chat_callbacks[task_id] = websocket

    # 通知客户端：任务已接受
    await safe_send_json(websocket, {
        "type": "chat_to_duck_accepted",
        "duck_id": duck_id,
        "task_id": task_id,
        "session_id": session_id,
    })

    # 标记 Duck 忙碌（direct_chat）
    await registry.set_current_task(duck_id, task_id, busy_reason="direct_chat")

    async def _on_task_done(task):
        """scheduler 回调：结果路由回用户 WebSocket"""
        target_ws = _duck_direct_chat_callbacks.pop(task_id, None)
        # 无论回调 WebSocket 是否存在，都要解除 Duck 的 busy 状态
        await registry.set_current_task(duck_id, None)
        if target_ws is None:
            return
        from services.duck_protocol import TaskStatus
        payload = {
            "type": "chat_to_duck_result",
            "duck_id": duck_id,
            "task_id": task_id,
            "session_id": session_id,
            "is_direct_chat": True,
            "success": task.status == TaskStatus.COMPLETED,
            "output": task.output,
            "error": task.error,
        }
        await safe_send_json(target_ws, payload)

    try:
        if duck.is_local:
            # 本地 Duck：通过调度器提交（内存队列）
            from services.duck_task_scheduler import get_task_scheduler, ScheduleStrategy
            scheduler = get_task_scheduler()
            await scheduler.initialize()
            await scheduler.submit(
                description=content,
                task_type="chat",
                timeout=600,
                strategy=ScheduleStrategy.DIRECT,
                target_duck_id=duck_id,
                callback=_on_task_done,
            )
        else:
            # 远程 Duck：通过 WebSocket 发送 TASK 消息
            from routes.duck_ws import send_to_duck
            from services.duck_task_scheduler import get_task_scheduler
            payload_model = DuckTaskPayload(
                task_id=task_id,
                description=content,
                task_type="chat",
                timeout=600,
            )
            msg = DuckMessage(
                type=DuckMessageType.TASK,
                duck_id=duck_id,
                payload=payload_model.model_dump(),
            )
            ok = await send_to_duck(duck_id, msg)
            if not ok:
                # 发送失败，恢复状态并通知
                await registry.set_current_task(duck_id, None)
                _duck_direct_chat_callbacks.pop(task_id, None)
                await safe_send_json(websocket, {
                    "type": "chat_to_duck_error",
                    "duck_id": duck_id,
                    "task_id": task_id,
                    "error": "无法连接到该 Duck，WebSocket 通道不可用",
                })
                return
            # 注册到调度器回调，等待 duck_ws._handle_result 触发
            scheduler = get_task_scheduler()
            await scheduler.initialize()
            # 直接将 on_task_done 注册到全局回调字典
            scheduler._callbacks[task_id] = _on_task_done
            # 同时将任务写入调度器使其能超时
            from services.duck_protocol import DuckTask
            stub_task = DuckTask(
                task_id=task_id,  # type: ignore[call-arg]
                description=content,
                task_type="chat",
                timeout=600,
                assigned_duck_id=duck_id,
            )
            scheduler._tasks[task_id] = stub_task
            scheduler._persist_task(stub_task)
            # 启动超时
            handle = asyncio.create_task(scheduler._timeout_watcher(task_id, 600))
            scheduler._timeout_handles[task_id] = handle

    except Exception as e:
        await registry.set_current_task(duck_id, None)
        _duck_direct_chat_callbacks.pop(task_id, None)
        logger.exception("chat_to_duck error")
        await safe_send_json(websocket, {
            "type": "chat_to_duck_error",
            "duck_id": duck_id,
            "task_id": task_id,
            "error": str(e),
        })


# ============== Server-side Heartbeat ==============

async def _heartbeat_loop(websocket: WebSocket, client_id: str):
    """服务端定时发送心跳，检测连接是否存活
    
    改进：基于上次发送完成时间计算下一次发送，避免心跳堆积
    """
    import time
    
    try:
        last_send_time = time.monotonic()
        while True:
            # 计算需要等待的时间（基于上次发送完成时间）
            elapsed = time.monotonic() - last_send_time
            wait_time = max(0, HEARTBEAT_INTERVAL - elapsed)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            # 发送心跳
            send_start = time.monotonic()
            success = await safe_send_json(websocket, {
                "type": "server_ping",
                "timestamp": datetime.now().isoformat(),
            })
            last_send_time = time.monotonic()
            
            if not success:
                logger.info(f"Heartbeat failed for {client_id}, connection likely dead")
                break
            
            # 如果发送时间超过 5 秒，记录警告
            send_duration = last_send_time - send_start
            if send_duration > 5:
                logger.warning(f"Heartbeat send took {send_duration:.1f}s for {client_id}, network may be slow")
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

    # 通知持久化管理器客户端已重连，取消孤儿任务超时计时器
    persistence = get_persistence_manager()
    await persistence.mark_client_reconnected(current_session_id)

    # 检查该 session 是否有正在运行的任务
    tracker = get_task_tracker()
    running_task = tracker.get_by_session(current_session_id)
    has_running_task = running_task and running_task.status == AutoTaskStatus.RUNNING

    running_chat = tracker.get_by_session(current_session_id, task_type=TaskType.CHAT)
    has_running_chat = running_chat and running_chat.status == AutoTaskStatus.RUNNING
    
    # 检查是否有缓冲的 chat 消息（即使任务已完成）
    has_buffered_chat = False
    buffered_chat_count = 0
    if running_chat:
        buffered = tracker.get_buffered_chunks(running_chat.task_id)
        buffered_chat_count = len(buffered)
        has_buffered_chat = buffered_chat_count > 0

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
        "has_buffered_chat": has_buffered_chat,
        "buffered_chat_count": buffered_chat_count,
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
                if new_sid and new_sid != current_session_id:
                    # 当 chat 消息携带不同 session_id 时，同步更新 connection_manager 的 session 注册，
                    # 确保 broadcast_to_session 能正确路由 duck_task_complete 等异步通知
                    await connection_manager.update_session(actual_client_id, new_sid)
                    current_session_id = new_sid
                elif new_sid:
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

            elif msg_type == "chat_to_duck":
                await _handle_chat_to_duck(message, websocket, current_session_id)

            else:
                # 未知消息类型，通知客户端
                logger.warning(f"Unknown message type received: {msg_type}")
                await safe_send_json(websocket, {
                    "type": "error",
                    "code": "unknown_message_type",
                    "message": f"未知的消息类型: {msg_type}",
                    "supported_types": [
                        "stop", "chat", "ping", "pong", "new_session", "clear_session",
                        "autonomous_task", "resume_task", "resume_chat", "get_episodes",
                        "get_statistics", "get_system_messages", "mark_system_message_read",
                        "mark_all_system_messages_read", "get_model_stats", "analyze_task",
                        "chat_to_duck"
                    ]
                })

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
        # 清理 per-WebSocket 写锁，防止内存泄漏
        remove_ws_write_lock(websocket)

        remaining = connection_manager.get_session_client_count(current_session_id)
        if remaining == 0:
            # 不立即取消任务，改为延迟取消策略
            await _handle_client_disconnect(current_session_id)
