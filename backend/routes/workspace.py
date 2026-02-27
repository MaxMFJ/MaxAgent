"""Workspace 上下文上报 API - MacAgentApp 上报当前工作目录、打开的文件"""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from agent.workspace_context import get_workspace_context

router = APIRouter()


class WorkspaceUpdate(BaseModel):
    """Workspace 上报请求"""
    session_id: str = "default"
    cwd: Optional[str] = None
    open_files: Optional[List[str]] = None


@router.post("/workspace")
async def workspace_update(body: WorkspaceUpdate):
    """MacAgentApp 上报 workspace 信息，供 prompt 注入"""
    ctx = get_workspace_context()
    ctx.update(
        session_id=body.session_id,
        cwd=body.cwd,
        open_files=body.open_files,
    )
    return {"ok": True}


@router.get("/workspace/{session_id}")
async def workspace_get(session_id: str):
    """获取会话的 workspace 状态（调试用）"""
    ctx = get_workspace_context()
    state = ctx.get(session_id)
    if not state:
        return {"cwd": "", "open_files": []}
    return state.to_dict()
