"""Health / Status / Connections 路由"""
from fastapi import APIRouter

from app_state import get_server_status, get_llm_client, ENABLE_EVOMAP
from connection_manager import connection_manager

router = APIRouter()


@router.get("/health")
async def health_check():
    llm = get_llm_client()
    evomap_status = "disabled"
    if ENABLE_EVOMAP:
        try:
            from agent.evomap_service import get_evomap_service
            evomap_ok = get_evomap_service()._initialized
            evomap_status = "connected" if evomap_ok else "initializing"
        except Exception:
            pass
    return {
        "status": "healthy",
        "server_status": get_server_status().value,
        "provider": llm.config.provider if llm else None,
        "model": llm.config.model if llm else None,
        "evomap": evomap_status,
    }


@router.get("/server-status")
async def server_status():
    return {"server_status": get_server_status().value}


@router.get("/connections")
async def get_connections():
    return connection_manager.get_stats()
