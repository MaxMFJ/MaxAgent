"""
Duck Client WebSocket — Duck 模式下的出向连接服务

When IS_DUCK_MODE=True, this service connects to the main agent's /duck/ws
endpoint as a WebSocket *client*, registers this Duck, maintains heartbeat,
and handles incoming TASK messages by delegating them to the local agent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import platform
import socket
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 重连退避参数
_RECONNECT_INITIAL_DELAY = 5   # 秒
_RECONNECT_MAX_DELAY = 60      # 秒
_HEARTBEAT_INTERVAL = 30       # 秒

# 全局任务引用，由 start_duck_client() 赋值
_client_task: Optional[asyncio.Task] = None


def _build_ws_url(main_agent_url: str) -> str:
    """将 HTTP/HTTPS URL 转换为 WebSocket URL，拼接 /duck/ws 路径。"""
    url = main_agent_url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[8:]
    elif url.startswith("http://"):
        url = "ws://" + url[7:]
    # 如果已经是 ws:// / wss:// 则保留
    return url + "/duck/ws"


async def _send(ws, msg_dict: dict) -> bool:
    """向 WebSocket 发送 JSON 消息，出错返回 False。"""
    try:
        import websockets
        await ws.send(json.dumps(msg_dict))
        return True
    except Exception as e:
        logger.debug("Duck WS send error: %s", e)
        return False


async def _heartbeat_loop(ws, duck_id: str):
    """每 HEARTBEAT_INTERVAL 秒向主 Backend 发送心跳。"""
    from services.duck_protocol import DuckMessage, DuckMessageType
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            msg = DuckMessage(type=DuckMessageType.HEARTBEAT, duck_id=duck_id)
            ok = await _send(ws, msg.model_dump())
            if not ok:
                break
    except asyncio.CancelledError:
        pass


async def _execute_duck_task(duck_id: str, task_payload: dict, ws) -> None:
    """
    接收主 Agent 下发的 TASK，使用本地 AutonomousAgent 执行，并将 RESULT 回传。
    """
    from services.duck_protocol import (
        DuckMessage, DuckMessageType,
        DuckTaskPayload, DuckResultPayload,
    )

    task_id = task_payload.get("task_id", "unknown")
    description = task_payload.get("description", "")
    timeout = int(task_payload.get("timeout", 600))
    start_time = time.time()

    logger.info("[Duck] Received TASK %s: %s", task_id, description[:120])

    try:
        task_payload_model = DuckTaskPayload(
            task_id=task_id,
            description=description,
            task_type=task_payload.get("task_type", "general"),
            params=task_payload.get("params", {}),
            priority=task_payload.get("priority", 0),
            timeout=timeout,
        )
    except Exception as e:
        logger.warning("[Duck] Invalid TASK payload: %s", e)

    try:
        from app_state import get_autonomous_agent
        agent = get_autonomous_agent()
        if agent is None:
            raise RuntimeError("Local AutonomousAgent not initialized")

        result_text = await asyncio.wait_for(
            agent.run(description),
            timeout=float(timeout),
        )
        success = True
        error = None
        output = result_text
    except asyncio.TimeoutError:
        success = False
        error = f"Task timed out after {timeout}s"
        output = None
        logger.warning("[Duck] Task %s timed out", task_id)
    except Exception as exc:
        success = False
        error = str(exc)
        output = None
        logger.exception("[Duck] Task %s execution error", task_id)

    duration = time.time() - start_time
    result = DuckResultPayload(
        task_id=task_id,
        success=success,
        output=output,
        error=error,
        duration=duration,
    )
    msg = DuckMessage(
        type=DuckMessageType.RESULT,
        duck_id=duck_id,
        payload=result.model_dump(),
    )
    await _send(ws, msg.model_dump())
    logger.info("[Duck] Task %s result sent (success=%s, %.1fs)", task_id, success, duration)


async def _run_duck_client(ws_url: str, token: str, duck_id: str, duck_type: str, duck_name: str):
    """
    主循环：连接 WebSocket 并处理消息，直到连接断开。
    返回时调用者负责重连。
    """
    import websockets
    from services.duck_protocol import (
        DuckMessage, DuckMessageType,
        DuckRegisterPayload,
    )

    full_url = f"{ws_url}?token={token}&duck_id={duck_id}"
    logger.info("[Duck] Connecting to main agent: %s", ws_url)

    async with websockets.connect(
        full_url,
        ping_interval=None,   # 我们自己管心跳
        close_timeout=10,
        open_timeout=15,
    ) as ws:
        logger.info("[Duck] Connected to main agent as duck_id=%s", duck_id)

        # 注册
        reg_payload = DuckRegisterPayload(
            duck_type=duck_type,
            name=duck_name or duck_id,
            skills=[],
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            token=token,
        )
        reg_msg = DuckMessage(
            type=DuckMessageType.REGISTER,
            duck_id=duck_id,
            payload=reg_payload.model_dump(),
        )
        await _send(ws, reg_msg.model_dump())
        logger.info("[Duck] REGISTER sent")

        # 启动心跳
        hb_task = asyncio.create_task(_heartbeat_loop(ws, duck_id))

        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type", "")

                if msg_type == DuckMessageType.TASK:
                    payload = data.get("payload", {})
                    # 每个任务独立 Task，不阻塞心跳循环
                    asyncio.create_task(_execute_duck_task(duck_id, payload, ws))

                elif msg_type == DuckMessageType.PING:
                    # 响应 PING → ACK
                    ack = DuckMessage(
                        type=DuckMessageType.ACK,
                        duck_id=duck_id,
                        payload={"ref": data.get("msg_id")},
                    )
                    await _send(ws, ack.model_dump())

                elif msg_type == DuckMessageType.CANCEL_TASK:
                    # 暂不实现任务取消（todo: 追踪 task -> asyncio.Task 映射）
                    logger.info("[Duck] CANCEL_TASK received (not yet impl): %s", data.get("payload", {}))

                elif msg_type == DuckMessageType.ACK:
                    pass  # 忽略

                else:
                    logger.debug("[Duck] Unknown message type: %s", msg_type)
        finally:
            hb_task.cancel()


async def start_duck_client() -> None:
    """
    Duck 模式下的 WebSocket 客户端守护协程。
    读取 app_state 中的 Duck 配置，连接主 Agent，自动重连。
    应由 main.py lifespan 通过 asyncio.create_task() 启动。
    """
    from app_state import (
        IS_DUCK_MODE,
        DUCK_MAIN_AGENT_URL,
        DUCK_TOKEN,
        DUCK_ID,
        DUCK_TYPE,
        DUCK_NAME,
    )

    if not IS_DUCK_MODE:
        return

    if not DUCK_MAIN_AGENT_URL:
        logger.warning("[Duck] DUCK_MAIN_AGENT_URL not set — duck client will not connect")
        return

    ws_url = _build_ws_url(DUCK_MAIN_AGENT_URL)
    delay = _RECONNECT_INITIAL_DELAY

    while True:
        try:
            await _run_duck_client(
                ws_url=ws_url,
                token=DUCK_TOKEN,
                duck_id=DUCK_ID,
                duck_type=DUCK_TYPE,
                duck_name=DUCK_NAME,
            )
            logger.info("[Duck] WS connection closed, reconnecting in %ss...", delay)
        except asyncio.CancelledError:
            logger.info("[Duck] Duck client task cancelled")
            return
        except Exception as e:
            logger.warning("[Duck] WS connection error: %s — reconnecting in %ss...", e, delay)

        await asyncio.sleep(delay)
        delay = min(delay * 2, _RECONNECT_MAX_DELAY)
