"""升级 / 重启路由"""
import asyncio
import logging
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_state import get_server_status, set_server_status, ServerStatus
from connection_manager import broadcast_status_change, broadcast_upgrade_message
from agent.system_message_service import get_system_message_service, MessageCategory

logger = logging.getLogger(__name__)

router = APIRouter()


class UpgradeTriggerRequest(BaseModel):
    reason: str
    user_message: str


class SelfUpgradeRequest(BaseModel):
    goal: str


async def trigger_tool_upgrade(reason: str, user_message: str, session_id: str = "default"):
    """触发工具自我升级流程"""
    set_server_status(ServerStatus.UPGRADING)
    await broadcast_status_change("upgrading", "正在规划升级方案...")
    try:
        from agent.self_upgrade import upgrade
        goal = f"{reason}" + (f"\n用户请求: {user_message}" if user_message else "")
        async for progress in upgrade(goal):
            logger.info(f"Upgrade: {progress.get('type')} {progress.get('phase', '')}")
            if progress.get("type") == "upgrade_complete":
                await broadcast_upgrade_message(progress)
                await broadcast_status_change("normal", "升级完成")
                try:
                    plan = progress.get("plan", "")
                    loaded = progress.get("loaded_tools", [])
                    content = "已加载工具: " + ", ".join(loaded) if loaded else (plan or "升级已完成")
                    get_system_message_service().add_info(
                        "进化/升级完成", content,
                        source="upgrade", category=MessageCategory.EVOLUTION.value,
                    )
                except Exception as e:
                    logger.warning(f"System notification for upgrade_complete failed: {e}")
            elif progress.get("type") == "upgrade_error":
                await broadcast_upgrade_message(progress)
                err = progress.get("error", "")
                await broadcast_status_change("normal", f"升级失败: {err}")
                try:
                    get_system_message_service().add_error(
                        "进化/升级失败", err or "未知错误",
                        source="upgrade", category=MessageCategory.EVOLUTION.value,
                    )
                except Exception as e:
                    logger.warning(f"System notification for upgrade_error failed: {e}")
    except Exception as e:
        logger.exception("Tool upgrade trigger failed")
        await broadcast_status_change("normal", f"升级失败: {str(e)}")
        await broadcast_upgrade_message({"type": "upgrade_error", "error": str(e)})
        try:
            get_system_message_service().add_error(
                "进化/升级失败", str(e),
                source="upgrade", category=MessageCategory.EVOLUTION.value,
            )
        except Exception:
            pass
    finally:
        set_server_status(ServerStatus.NORMAL)


async def trigger_restart(delay_seconds: int = 5):
    set_server_status(ServerStatus.RESTARTING)
    await broadcast_status_change("restarting", "系统即将重启，请稍候...")
    await broadcast_upgrade_message({
        "type": "content",
        "content": "⏳ 系统即将重启，请稍候重连...",
        "is_system": True,
    })
    try:
        get_system_message_service().add_info(
            "系统即将重启",
            f"将在 {delay_seconds} 秒后重启，请稍候重连。",
            source="restart", category=MessageCategory.EVOLUTION.value,
        )
    except Exception:
        pass
    logger.info(f"Restarting in {delay_seconds}s...")
    await asyncio.sleep(delay_seconds)
    sys.exit(0)


@router.post("/upgrade/self")
async def trigger_self_upgrade(request: SelfUpgradeRequest):
    if get_server_status() == ServerStatus.UPGRADING:
        raise HTTPException(status_code=409, detail="升级已在进行中")
    asyncio.create_task(trigger_tool_upgrade(request.goal, "", "default"))
    return {"status": "started", "goal": request.goal}


@router.post("/upgrade/trigger")
async def trigger_upgrade_endpoint(request: UpgradeTriggerRequest):
    if get_server_status() == ServerStatus.UPGRADING:
        raise HTTPException(status_code=409, detail="升级已在进行中")
    asyncio.create_task(trigger_tool_upgrade(request.reason, request.user_message, "default"))
    return {"status": "triggered", "message": "升级流程已启动"}


@router.post("/upgrade/restart")
async def trigger_restart_endpoint(delay: int = 5):
    if get_server_status() == ServerStatus.UPGRADING:
        raise HTTPException(status_code=409, detail="升级进行中，请稍后再试")
    asyncio.create_task(trigger_restart(min(max(delay, 2), 30)))
    return {"status": "triggered", "message": f"将在 {delay} 秒后重启"}
