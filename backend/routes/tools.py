"""工具管理路由：列表、审批、重载"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_state import get_agent_core
from connection_manager import connection_manager

router = APIRouter()


def _load_generated_tools() -> list:
    """动态加载 tools/generated/ 下的新工具，并同步 schema_registry"""
    agent_core = get_agent_core()
    if not agent_core:
        return []
    loaded = agent_core.registry.load_generated_tools(agent_core.runtime_adapter)
    from tools.schema_registry import build_from_base_tools
    build_from_base_tools(agent_core.registry.list_tools())
    return loaded


class ToolApproveRequest(BaseModel):
    tool_name: str
    file_path: Optional[str] = None


@router.get("/tools")
async def list_tools():
    agent_core = get_agent_core()
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return {"tools": [tool.to_function_schema() for tool in agent_core.tools]}


@router.get("/tools/pending")
async def list_pending_tools():
    try:
        from agent.upgrade_security import list_pending_tool_approvals
        pending = list_pending_tool_approvals()
        return {"pending": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/approve")
async def approve_tool(request: ToolApproveRequest):
    try:
        from agent.upgrade_security import approve_tool as do_approve
        fp = request.file_path
        if not fp:
            fp = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "tools", "generated",
                f"{request.tool_name.replace('_tool', '')}_tool.py",
            )
            if not os.path.exists(fp):
                fp = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), "tools", "generated",
                    f"{request.tool_name}.py",
                )
        ok, msg = do_approve(fp, request.tool_name)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "approved", "message": msg}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/reload")
async def reload_tools():
    agent_core = get_agent_core()
    if not agent_core:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    loaded = _load_generated_tools()
    await connection_manager.broadcast_all({"type": "tools_updated"})
    return {"status": "ok", "loaded_tools": loaded}
