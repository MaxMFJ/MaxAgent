"""Self-Healing 路由 + WebSocket"""
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent.self_healing import get_self_healing_agent, get_diagnostic_engine

logger = logging.getLogger(__name__)

router = APIRouter()


class DiagnoseRequest(BaseModel):
    error_message: str
    stack_trace: str = ""
    context: Optional[dict] = None


class HealRequest(BaseModel):
    error_message: str
    stack_trace: str = ""
    context: Optional[dict] = None
    auto_confirm: bool = False


@router.get("/self-healing/status")
async def self_healing_status():
    agent = get_self_healing_agent()
    return {
        "current_status": agent.current_status.value,
        "statistics": agent.get_statistics(),
        "recent_healings": agent.get_recent_healings(5),
    }


@router.post("/self-healing/diagnose")
async def diagnose_problem(request: DiagnoseRequest):
    engine = get_diagnostic_engine()
    result = engine.diagnose(
        error_message=request.error_message,
        stack_trace=request.stack_trace,
        context=request.context or {},
    )
    return result.to_dict()


@router.post("/self-healing/plan")
async def create_repair_plan(request: DiagnoseRequest):
    agent = get_self_healing_agent()
    diagnostic = agent.diagnose_only(
        error_message=request.error_message,
        stack_trace=request.stack_trace,
        context=request.context or {},
    )
    plan = agent.plan_only(diagnostic, request.context or {})
    return {
        "diagnostic": diagnostic.to_dict(),
        "plan": plan.to_dict(),
    }


@router.websocket("/ws/self-healing")
async def self_healing_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Self-healing WebSocket connected")

    try:
        while True:
            message = await websocket.receive_json()

            if message.get("type") == "heal":
                agent = get_self_healing_agent()
                async for update in agent.heal(
                    error_message=message.get("error_message", ""),
                    stack_trace=message.get("stack_trace", ""),
                    context={
                        **(message.get("context") or {}),
                        "auto_confirm": message.get("auto_confirm", False),
                        "confirmed": message.get("confirmed", False),
                    },
                ):
                    await websocket.send_json(update)

            elif message.get("type") == "confirm":
                await websocket.send_json({
                    "type": "confirmation_received",
                    "message": "确认已收到，继续执行修复...",
                })

            elif message.get("type") == "get_statistics":
                agent = get_self_healing_agent()
                await websocket.send_json({
                    "type": "statistics",
                    "data": agent.get_statistics(),
                })

            elif message.get("type") == "get_history":
                agent = get_self_healing_agent()
                count = message.get("count", 10)
                await websocket.send_json({
                    "type": "history",
                    "data": agent.get_recent_healings(count),
                })

    except WebSocketDisconnect:
        logger.info("Self-healing WebSocket disconnected")
    except Exception as e:
        logger.error(f"Self-healing WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
