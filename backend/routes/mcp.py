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


# ---------------------------------------------------------------------------
# MCP 目录（Catalog）接口
# ---------------------------------------------------------------------------

@router.get("/mcp/catalog")
async def list_catalog(query: str = "", category: str = ""):
    """搜索 MCP 目录。"""
    from services.mcp_catalog_service import get_mcp_catalog
    catalog = get_mcp_catalog()
    if category:
        results = catalog.search_by_category(category)
    elif query:
        results = catalog.search(query, limit=10)
    else:
        results = catalog.get_all()
    return {
        "results": [e.to_dict() for e in results],
        "total": len(results),
        "categories": catalog.list_categories(),
    }


@router.get("/mcp/catalog/{mcp_id}")
async def get_catalog_entry(mcp_id: str):
    """获取单个 MCP Server 条目信息。"""
    from services.mcp_catalog_service import get_mcp_catalog
    entry = get_mcp_catalog().get_entry(mcp_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未找到 MCP: {mcp_id}")
    return entry.to_dict()


class InstallFromCatalogRequest(BaseModel):
    mcp_id: str = Field(..., description="目录中的 MCP ID")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量（如 API Key）")


@router.post("/mcp/catalog/install")
async def install_from_catalog(req: InstallFromCatalogRequest):
    """从目录安装 MCP Server（跳过 HITL，用于前端直接操作）。"""
    from services.mcp_catalog_service import get_mcp_catalog
    catalog = get_mcp_catalog()
    entry = catalog.get_entry(req.mcp_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未找到 MCP: {req.mcp_id}")

    # 构建配置
    cfg = MCPServerConfig(
        name=entry.id,
        transport=entry.transport,
        command=entry.command,
        env=req.env,
        url="",
        headers={},
        timeout=30.0,
    )
    try:
        conn = await get_mcp_manager().add_server(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装 MCP 失败: {e}")

    _sync_mcp_to_registry()
    return {
        "status": "installed",
        "name": entry.id,
        "tools": [t.to_dict() for t in conn.tools],
    }
