"""Session Resume / Fork REST API"""
from typing import Optional

from fastapi import APIRouter, HTTPException

from services.session_service import get_session_service

router = APIRouter()


@router.get("/sessions")
async def list_sessions():
    """列出所有可恢复的会话"""
    svc = get_session_service()
    sessions = await svc.list_resumable_sessions()
    return {"sessions": sessions}


@router.get("/sessions/{session_id}/checkpoints")
async def list_checkpoints(session_id: str):
    """列出会话的检查点"""
    svc = get_session_service()
    checkpoints = await svc.list_checkpoints(session_id)
    return {"checkpoints": checkpoints, "session_id": session_id}


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str, checkpoint_id: Optional[str] = None):
    """恢复会话执行"""
    svc = get_session_service()
    result = await svc.resume_session(session_id, checkpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No checkpoint found for this session")
    return result


@router.post("/sessions/{session_id}/fork")
async def fork_session(session_id: str, checkpoint_id: Optional[str] = None):
    """从检查点分支新会话"""
    svc = get_session_service()
    result = await svc.fork_session(session_id, checkpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No checkpoint found for this session")
    return result
