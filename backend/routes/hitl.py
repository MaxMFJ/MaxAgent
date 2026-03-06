"""HITL REST API — 查询待确认、确认、拒绝"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from services.hitl_service import get_hitl_manager

router = APIRouter()


@router.get("/hitl/pending")
async def list_pending(session_id: Optional[str] = None):
    """查询当前等待确认的动作列表"""
    mgr = get_hitl_manager()
    return {"pending": mgr.get_pending(session_id)}


@router.post("/hitl/confirm/{action_id}")
async def confirm_action(action_id: str):
    """确认执行某动作"""
    mgr = get_hitl_manager()
    ok = mgr.confirm(action_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No pending request for this action_id")
    return {"status": "approved", "action_id": action_id}


@router.post("/hitl/reject/{action_id}")
async def reject_action(action_id: str):
    """拒绝执行某动作"""
    mgr = get_hitl_manager()
    ok = mgr.reject(action_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No pending request for this action_id")
    return {"status": "rejected", "action_id": action_id}
