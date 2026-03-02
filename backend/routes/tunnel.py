"""
Cloudflare Tunnel 管理路由
提供 Tunnel 状态查询、启动/停止/重启、局域网信息、自动启动配置
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(tags=["tunnel"])


def _get_svc():
    from services.tunnel_lifecycle import get_tunnel_lifecycle
    return get_tunnel_lifecycle()


# ── 数据模型 ────────────────────────────────────

class AutoStartConfig(BaseModel):
    enabled: bool


# ── 路由 ────────────────────────────────────────

@router.get("/tunnel/status")
async def tunnel_status():
    """获取 Tunnel 完整状态"""
    svc = _get_svc()
    return svc.get_status()


@router.post("/tunnel/start")
async def tunnel_start():
    """手动启动 Tunnel"""
    svc = _get_svc()
    result = await svc.start_tunnel()
    return result


@router.post("/tunnel/stop")
async def tunnel_stop():
    """手动停止 Tunnel"""
    svc = _get_svc()
    result = await svc.stop_tunnel()
    return result


@router.post("/tunnel/restart")
async def tunnel_restart():
    """手动重启 Tunnel（停止后再启动）"""
    svc = _get_svc()
    result = await svc.restart_tunnel()
    return result


@router.get("/tunnel/lan-info")
async def tunnel_lan_info():
    """获取局域网连接信息"""
    svc = _get_svc()
    return svc._get_lan_info()


@router.post("/tunnel/auto-start")
async def tunnel_auto_start(config: AutoStartConfig):
    """设置是否随后端自动启动 Tunnel"""
    svc = _get_svc()
    svc.set_auto_start(config.enabled)
    return {"ok": True, "auto_start": config.enabled}


@router.get("/tunnel/auto-start")
async def tunnel_auto_start_status():
    """查询自动启动配置"""
    svc = _get_svc()
    return {"auto_start": svc._auto_start_enabled}
