"""
Duck WebSocket 端点  /duck/ws
处理 Duck Agent 的连接、注册、心跳、任务结果等消息。
"""
import asyncio
import json
import logging
import uuid

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from auth import verify_token
from connection_manager import connection_manager, safe_send_json, ClientType
from services.duck_protocol import (
    DuckInfo,
    DuckMessage,
    DuckMessageType,
    DuckRegisterPayload,
    DuckResultPayload,
    DuckStatus,
    DuckType,
)
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

# duck_id → WebSocket 映射（用于主动推送任务）
_duck_websockets: dict[str, WebSocket] = {}

HEARTBEAT_INTERVAL = 30


def get_duck_websocket(duck_id: str) -> Optional[WebSocket]:
    """获取指定 Duck 的 WebSocket 连接"""
    return _duck_websockets.get(duck_id)


async def send_to_duck(duck_id: str, message: DuckMessage) -> bool:
    """向指定 Duck 发送消息"""
    ws = _duck_websockets.get(duck_id)
    if ws is None:
        return False
    return await safe_send_json(ws, message.model_dump())


# ─── WebSocket 端点 ──────────────────────────────────

@router.websocket("/duck/ws")
async def duck_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
    duck_id: str = Query(default=""),
):
    # 认证
    if not verify_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    if not duck_id:
        duck_id = f"duck_{uuid.uuid4().hex[:8]}"

    _duck_websockets[duck_id] = websocket
    logger.info(f"Duck WebSocket connected: {duck_id}")

    # 心跳任务
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, duck_id))

    registry = DuckRegistry.get_instance()
    await registry.initialize()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Duck {duck_id}: invalid JSON")
                continue

            msg_type = data.get("type", "")

            if msg_type == DuckMessageType.REGISTER:
                await _handle_register(websocket, duck_id, data)
            elif msg_type == DuckMessageType.HEARTBEAT:
                await registry.heartbeat(duck_id)
            elif msg_type == DuckMessageType.RESULT:
                await _handle_result(duck_id, data)
            elif msg_type == DuckMessageType.STATUS_REPORT:
                await _handle_status_report(duck_id, data)
            elif msg_type == DuckMessageType.CHAT:
                await _handle_chat(duck_id, data)
            else:
                logger.debug(f"Duck {duck_id}: unknown message type '{msg_type}'")

    except WebSocketDisconnect:
        logger.info(f"Duck WebSocket disconnected: {duck_id}")
    except Exception as e:
        logger.error(f"Duck WebSocket error ({duck_id}): {e}")
    finally:
        heartbeat_task.cancel()
        _duck_websockets.pop(duck_id, None)
        await registry.set_status(duck_id, DuckStatus.OFFLINE)


# ─── 心跳 ────────────────────────────────────────────

async def _heartbeat_loop(websocket: WebSocket, duck_id: str):
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            msg = DuckMessage(type=DuckMessageType.PING, duck_id=duck_id)
            await safe_send_json(websocket, msg.model_dump())
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


# ─── 消息 Handlers ───────────────────────────────────

async def _handle_register(websocket: WebSocket, duck_id: str, data: dict):
    registry = DuckRegistry.get_instance()
    payload = data.get("payload", {})

    try:
        reg = DuckRegisterPayload(**payload)
    except Exception:
        reg = DuckRegisterPayload()

    info = DuckInfo(
        duck_id=duck_id,
        name=reg.name or duck_id,
        duck_type=reg.duck_type,
        skills=reg.skills,
        hostname=reg.hostname,
        platform=reg.platform,
    )
    await registry.register(info)

    # 如果携带 Egg token，标记 Egg 已连接
    if reg.token:
        try:
            from services.egg_builder import get_egg_builder
            builder = get_egg_builder()
            builder.mark_connected(duck_id)
        except Exception:
            pass

    # 回复 ACK
    ack = DuckMessage(
        type=DuckMessageType.ACK,
        duck_id=duck_id,
        payload={"ref_type": "register", "duck_id": duck_id, "status": "ok"},
    )
    await safe_send_json(websocket, ack.model_dump())

    # 新 Duck 上线，触发调度器重新分配 PENDING 任务
    try:
        from services.duck_task_scheduler import get_task_scheduler
        scheduler = get_task_scheduler()
        await scheduler.reschedule_pending()
    except Exception:
        pass


async def _handle_result(duck_id: str, data: dict):
    """Duck 返回任务结果"""
    payload = data.get("payload", {})
    try:
        result = DuckResultPayload(**payload)
    except Exception as e:
        logger.warning(f"Duck {duck_id}: invalid result payload: {e}")
        return

    # 通过 task scheduler 处理结果（延迟导入避免循环依赖）
    try:
        from services.duck_task_scheduler import get_task_scheduler
        scheduler = get_task_scheduler()
        await scheduler.handle_result(duck_id, result)
    except ImportError:
        logger.debug("duck_task_scheduler not yet available")

    # 如果这是一个直聊任务（chat_to_duck），路由结果回发起方 WebSocket
    try:
        from ws_handler import _duck_direct_chat_callbacks
        target_ws = _duck_direct_chat_callbacks.pop(result.task_id, None)
        if target_ws is not None:
            await safe_send_json(target_ws, {
                "type": "chat_to_duck_result",
                "duck_id": duck_id,
                "task_id": result.task_id,
                "is_direct_chat": True,
                "success": result.success,
                "output": result.output,
                "error": result.error,
            })
    except ImportError:
        pass

    logger.info(f"Duck {duck_id} task result: task={result.task_id}, success={result.success}")


async def _handle_status_report(duck_id: str, data: dict):
    """Duck 上报当前状态"""
    payload = data.get("payload", {})
    status_str = payload.get("status", "")
    registry = DuckRegistry.get_instance()
    try:
        status = DuckStatus(status_str)
        await registry.set_status(duck_id, status)
    except ValueError:
        logger.warning(f"Duck {duck_id}: unknown status '{status_str}'")


async def _handle_chat(duck_id: str, data: dict):
    """Duck 发来的自由消息，广播给主会话"""
    payload = data.get("payload", {})
    message = payload.get("message", "")
    if not message:
        return
    # 广播给所有客户端
    event = {
        "type": "duck_chat",
        "duck_id": duck_id,
        "message": message,
    }
    await connection_manager.broadcast_all(event)
