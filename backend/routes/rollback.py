"""
Rollback 路由 — v3.4
列出操作快照并支持 undo 回滚。
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from agent.snapshot_manager import get_snapshot_manager

router = APIRouter()


class RollbackRequest(BaseModel):
    snapshot_id: str


@router.get("/rollback/snapshots")
async def list_snapshots(
    task_id: Optional[str] = Query(None, description="按 task_id 过滤"),
    session_id: Optional[str] = Query(None, description="按 session_id 过滤"),
    limit: int = Query(50, ge=1, le=200),
):
    """列出最近的文件操作快照（按时间倒序）。"""
    snapshots = get_snapshot_manager().list_snapshots(
        task_id=task_id,
        session_id=session_id,
        limit=limit,
    )
    return {"snapshots": snapshots, "total": len(snapshots)}


@router.post("/rollback")
async def rollback(req: RollbackRequest):
    """回滚指定快照，恢复文件到操作前的状态。"""
    result = get_snapshot_manager().rollback(req.snapshot_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.delete("/rollback/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    """删除一条快照记录（不恢复文件，仅删除记录）。"""
    ok = get_snapshot_manager().delete_snapshot(snapshot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="快照不存在")
    return {"success": True, "snapshot_id": snapshot_id}
