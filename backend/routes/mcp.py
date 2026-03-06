"""
MCP (Model Context Protocol) 路由 — v3.4
管理外部 MCP Server 的连接、工具列表与工具调用。
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from agent.mcp_client import get_mcp_manager, MCPServerConfig

logger = logging.getLogger(__name__)


def _sync_mcp_to_registry() -> int:
    """将 MCP 工具同步到 ToolRegistry（如果 AgentCore 已初始化）。"""
    try:
        from app_state import get_agent_core
        core = get_agent_core()
        if core is None:
            return 0
        from tools.mcp_adapter import sync_mcp_tools_to_registry
        synced = sync_mcp_tools_to_registry(core.registry, get_mcp_manager())
        logger.info("MCP→Registry synced %d tools", len(synced))
        return len(synced)
    except Exception as e:
        logger.warning("MCP→Registry sync failed: %s", e)
        return 0

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AddServerRequest(BaseModel):
    name: str = Field(..., description="服务器唯一标识符（如 'filesystem'）")
    transport: str = Field(..., description="传输方式: 'stdio' 或 'http'")
    command: List[str] = Field(default_factory=list, description="stdio 模式下的启动命令")
    env: Dict[str, str] = Field(default_factory=dict, description="传递给 stdio 进程的额外环境变量")
    url: str = Field(default="", description="HTTP 模式下的服务器 URL")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    timeout: float = Field(default=30.0, description="请求超时时间（秒）")


class CallToolRequest(BaseModel):
    server: str = Field(..., description="目标 MCP 服务器名称")
    tool: str = Field(..., description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/mcp/servers")
async def list_servers():
    """列出所有已配置的 MCP 服务器及其连接状态。"""
    return {"servers": get_mcp_manager().server_status()}


@router.post("/mcp/servers")
async def add_server(req: AddServerRequest):
    """添加并连接一个 MCP 服务器。"""
    manager = get_mcp_manager()
    cfg = MCPServerConfig(
        name=req.name,
        transport=req.transport,
        command=req.command,
        env=req.env,
        url=req.url,
        headers=req.headers,
        timeout=req.timeout,
    )
    try:
        conn = await manager.add_server(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接 MCP 服务器失败: {e}")
    # Unified Tool Router: 动态同步到 ToolRegistry
    _sync_mcp_to_registry()
    return {
        "status": "connected",
        "name": req.name,
        "tools": [t.to_dict() for t in conn.tools],
    }


@router.delete("/mcp/servers/{name}")
async def remove_server(name: str):
    """断开并移除一个 MCP 服务器。"""
    await get_mcp_manager().remove_server(name)
    # Unified Tool Router: 从 ToolRegistry 中移除该 server 的工具
    _sync_mcp_to_registry()
    return {"status": "removed", "name": name}


@router.get("/mcp/tools")
async def list_tools():
    """列出所有已连接 MCP 服务器提供的工具。"""
    tools = await get_mcp_manager().list_tools()
    return {"tools": tools, "total": len(tools)}


@router.post("/mcp/tools/call")
async def call_tool(req: CallToolRequest):
    """调用指定 MCP 服务器上的工具。"""
    try:
        result = await get_mcp_manager().call_tool(req.server, req.tool, req.arguments)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工具调用失败: {e}")
    return {"success": True, "result": result}
