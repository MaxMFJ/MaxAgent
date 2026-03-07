"""
MCP 目录搜索与安装请求工具
LLM 在判断需要额外 MCP 能力时调用此工具：
1. search_mcp_catalog — 搜索可用的 MCP Server
2. request_mcp_install — 发起安装请求（需用户审批）
"""

import uuid
import logging
from typing import Any, Dict

from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)


class MCPCatalogTool(BaseTool):
    """搜索 MCP 目录，查找可扩展的 MCP 能力"""

    name = "search_mcp_catalog"
    description = (
        "搜索可用的 MCP Server 扩展能力。当用户需要的功能（如网页搜索、数据库查询、"
        "代码仓库管理、浏览器自动化、文档转换等）不在当前已有工具中时，"
        "调用此工具查询可安装的 MCP Server。\n"
        "返回匹配的 MCP Server 列表，包含名称、描述、所需配置等信息。"
    )
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如「搜索」「数据库」「github」「browser」等"
            },
            "category": {
                "type": "string",
                "description": "按分类筛选（可选）: search/browser/database/developer/vision/knowledge/filesystem/communication/document/cloud/data-science/security/finance",
                "enum": [
                    "search", "browser", "database", "developer", "vision",
                    "knowledge", "filesystem", "communication", "document",
                    "cloud", "data-science", "security", "finance"
                ]
            }
        },
        "required": ["query"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        from services.mcp_catalog_service import get_mcp_catalog

        query = kwargs.get("query", "")
        category = kwargs.get("category")

        catalog = get_mcp_catalog()

        if category:
            results = catalog.search_by_category(category)
        else:
            results = catalog.search(query, limit=6)

        if not results:
            return ToolResult(
                success=True,
                data={
                    "results": [],
                    "message": f"未找到与「{query}」匹配的 MCP Server。",
                    "hint": "可以尝试不同关键词，或查看全部分类。",
                    "categories": catalog.list_categories(),
                }
            )

        # 检查哪些已安装
        from agent.mcp_client import get_mcp_manager
        manager = get_mcp_manager()
        installed_names = set()
        for s in manager.server_status():
            installed_names.add(s.get("name", ""))

        items = []
        for entry in results:
            item = {
                "id": entry.id,
                "name": entry.name,
                "description": entry.description,
                "category": entry.category,
                "env_required": entry.env_hint or "无",
                "installed": entry.id in installed_names,
            }
            if entry.id in installed_names:
                item["status"] = "✅ 已安装"
            else:
                item["status"] = "📦 可安装"
                item["install_hint"] = (
                    f"如需安装，请调用 request_mcp_install 工具，传入 mcp_id=\"{entry.id}\""
                )
            items.append(item)

        return ToolResult(
            success=True,
            data={
                "results": items,
                "total": len(items),
                "message": f"找到 {len(items)} 个匹配的 MCP Server。"
            }
        )


class RequestMCPInstallTool(BaseTool):
    """请求安装 MCP Server（提交审批，等待用户确认）"""

    name = "request_mcp_install"
    description = (
        "请求安装一个 MCP Server 扩展能力。安装请求会提交给用户审批，"
        "用户确认后系统自动完成安装和连接。\n"
        "调用前必须先用 search_mcp_catalog 搜索到可用的 MCP Server。"
    )
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "mcp_id": {
                "type": "string",
                "description": "要安装的 MCP Server ID（从 search_mcp_catalog 结果中获取）"
            },
            "reason": {
                "type": "string",
                "description": "说明为什么需要安装此 MCP，简要描述用途"
            },
            "env_vars": {
                "type": "object",
                "description": "需要的环境变量（如 API Key），由用户提供",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["mcp_id", "reason"]
    }

    async def execute(self, **kwargs) -> ToolResult:
        from services.mcp_catalog_service import get_mcp_catalog
        from agent.mcp_client import get_mcp_manager

        mcp_id = kwargs.get("mcp_id", "")
        reason = kwargs.get("reason", "")
        env_vars = kwargs.get("env_vars") or {}

        if not mcp_id:
            return ToolResult(success=False, error="mcp_id 不能为空")

        catalog = get_mcp_catalog()
        entry = catalog.get_entry(mcp_id)
        if not entry:
            return ToolResult(
                success=False,
                error=f"未找到 MCP Server: {mcp_id}，请先用 search_mcp_catalog 搜索。"
            )

        # 检查是否已安装
        manager = get_mcp_manager()
        for s in manager.server_status():
            if s.get("name") == mcp_id:
                return ToolResult(
                    success=True,
                    data={
                        "status": "already_installed",
                        "mcp_id": mcp_id,
                        "message": f"MCP Server「{entry.name}」已安装，无需重复安装。"
                    }
                )

        # 检查是否需要 env_vars
        if entry.env_hint and not env_vars.get(entry.env_hint):
            return ToolResult(
                success=True,
                data={
                    "status": "env_required",
                    "mcp_id": mcp_id,
                    "env_hint": entry.env_hint,
                    "message": (
                        f"安装「{entry.name}」需要环境变量 {entry.env_hint}。"
                        f"请让用户提供该值后再次调用。"
                    )
                }
            )

        # 创建审批请求
        action_id = f"mcp_install_{uuid.uuid4().hex[:8]}"

        try:
            from services.hitl_service import get_hitl_manager, HitlDecision

            hitl = get_hitl_manager()
            params = {
                "mcp_id": mcp_id,
                "name": entry.name,
                "description": entry.description,
                "command": entry.command,
                "env_vars": env_vars,
                "reason": reason,
            }
            req = hitl.create_request(
                action_id=action_id,
                task_id=kwargs.get("_task_id", ""),
                session_id=kwargs.get("_session_id", ""),
                action_type="mcp_install",
                params=params,
            )

            # 广播审批请求到前端
            try:
                from connection_manager import manager as ws_manager
                import json
                import asyncio
                asyncio.ensure_future(ws_manager.broadcast(json.dumps({
                    "type": "hitl_request",
                    "data": {
                        **req.to_dict(),
                        "display": {
                            "title": f"安装 MCP: {entry.name}",
                            "detail": f"{entry.description}\n原因: {reason}",
                            "risk_level": "medium",
                        }
                    }
                })))
            except Exception as e:
                logger.warning("Failed to broadcast HITL request: %s", e)

            # 等待用户审批
            decision = await hitl.wait_for_decision(action_id)

            if decision == HitlDecision.APPROVED:
                # 执行安装
                install_result = await self._do_install(entry, env_vars)
                return install_result
            elif decision == HitlDecision.REJECTED:
                return ToolResult(
                    success=True,
                    data={
                        "status": "rejected",
                        "mcp_id": mcp_id,
                        "message": f"用户拒绝了安装「{entry.name}」的请求。"
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    data={
                        "status": "timeout",
                        "mcp_id": mcp_id,
                        "message": f"安装「{entry.name}」的审批请求已超时，请重试。"
                    }
                )
        except ImportError:
            # HITL 不可用，直接安装（非正式环境）
            logger.warning("HITL service not available, installing directly")
            return await self._do_install(entry, env_vars)

    async def _do_install(
        self, entry: "MCPCatalogEntry", env_vars: Dict[str, str]
    ) -> ToolResult:
        """实际执行 MCP Server 安装"""
        from agent.mcp_client import get_mcp_manager, MCPServerConfig

        cfg = MCPServerConfig(
            name=entry.id,
            transport=entry.transport,
            command=entry.command,
            env=env_vars,
            url="",
            headers={},
            timeout=30.0,
        )

        try:
            manager = get_mcp_manager()
            conn = await manager.add_server(cfg)

            # 同步到 ToolRegistry
            try:
                from app_state import get_agent_core
                core = get_agent_core()
                if core:
                    from tools.mcp_adapter import sync_mcp_tools_to_registry
                    synced = sync_mcp_tools_to_registry(core.registry, manager)
                    logger.info("MCP install: synced %d tools", len(synced))
            except Exception as e:
                logger.warning("MCP install: registry sync failed: %s", e)

            tools = [t.to_dict() for t in conn.tools]
            return ToolResult(
                success=True,
                data={
                    "status": "installed",
                    "mcp_id": entry.id,
                    "name": entry.name,
                    "tools_count": len(tools),
                    "tools": [{"name": t.get("name", ""), "description": t.get("description", "")} for t in tools[:10]],
                    "message": (
                        f"✅ MCP Server「{entry.name}」安装成功！"
                        f"新增 {len(tools)} 个工具可用。"
                    )
                }
            )
        except Exception as e:
            logger.error("MCP install failed for %s: %s", entry.id, e)
            return ToolResult(
                success=False,
                error=f"安装「{entry.name}」失败: {str(e)}"
            )
