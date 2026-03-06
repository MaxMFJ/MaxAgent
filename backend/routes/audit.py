"""审计日志 REST API — 查询、统计、详情"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from services.audit_service import query_audit_logs, get_audit_stats, get_audit_event

router = APIRouter()


@router.get("/audit")
async def list_audit_logs(
    type: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """查询审计日志（支持多维过滤）"""
    logs = query_audit_logs(
        event_type=type,
        task_id=task_id,
        session_id=session_id,
        offset=offset,
        limit=min(limit, 1000),
        date_from=date_from,
        date_to=date_to,
    )
    return {"logs": logs, "count": len(logs), "offset": offset}


@router.get("/audit/stats")
async def audit_stats():
    """审计统计摘要"""
    return get_audit_stats()


@router.get("/audit/{log_id}")
async def get_audit_detail(log_id: str):
    """获取单条审计记录详情"""
    event = get_audit_event(log_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return event
