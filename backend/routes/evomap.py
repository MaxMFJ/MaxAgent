"""EvoMap 进化网络路由"""
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_state import ENABLE_EVOMAP

router = APIRouter()


def _require_evomap_enabled():
    if not ENABLE_EVOMAP:
        raise HTTPException(
            status_code=503,
            detail="EvoMap is disabled. Set ENABLE_EVOMAP=true to enable.",
        )


class EvoMapPublishRequest(BaseModel):
    tool_name: str
    strategy: List[str]
    signals: List[str] = []
    summary: str = ""


class EvoMapSearchRequest(BaseModel):
    signals: List[str]
    limit: int = 10
    min_confidence: float = 0.5


class EvoMapResolveRequest(BaseModel):
    task: str
    signals: Optional[List[str]] = None


@router.get("/evomap/status")
async def evomap_status():
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        return svc.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evomap/register")
async def evomap_register():
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        caps = [
            "app_control", "file_operation", "terminal", "browser",
            "screenshot", "system", "mail", "search",
        ]
        result = await svc.initialize(caps)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evomap/search")
async def evomap_search(request: EvoMapSearchRequest):
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        result = await svc.client.search_capsules(
            request.signals, limit=request.limit, min_confidence=request.min_confidence,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evomap/resolve")
async def evomap_resolve(request: EvoMapResolveRequest):
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        result = await svc.resolve_capability(request.task, request.signals)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evomap/publish")
async def evomap_publish(request: EvoMapPublishRequest):
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        result = await svc.publish_capability(
            tool_name=request.tool_name,
            strategy=request.strategy,
            signals=request.signals or [request.tool_name],
            summary=request.summary,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evomap/events")
async def evomap_events(limit: int = 50):
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        return {"events": svc.client.get_events(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evomap/audit")
async def evomap_audit(limit: int = 100):
    _require_evomap_enabled()
    try:
        from agent.evomap_service import get_evomap_service
        svc = get_evomap_service()
        return {"entries": svc.client.get_audit_log(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
