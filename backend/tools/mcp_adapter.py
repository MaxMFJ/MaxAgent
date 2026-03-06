"""
MCP Tool Adapter — Unified Tool Router 的核心
将 MCP Server 提供的工具包装为 BaseTool 并注入 ToolRegistry。

两种注册模式：
1. MCP-only 工具（如 github_*、code_runner_*）→ 直接注册为短名
2. 与内置重叠的 MCP 工具（如 browser_*、file_*）→ 注册为 mcp/{server}/{tool}，
   由 ToolRouter 内置失败时自动 fallback 使用

LLM 只看到内置 schema（短名）+ MCP-only schema（短名），
不会看到 mcp/ 前缀的备选工具，消除选择困惑。
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set

from .base import BaseTool, ToolCategory, ToolResult

logger = logging.getLogger(__name__)

# 内置工具名集合（与 backend/tools/ 下注册的工具名匹配时视为"重叠"）
# 运行时动态获取，此处仅做缓存
_builtin_names_cache: Optional[Set[str]] = None


def _get_builtin_names(registry) -> Set[str]:
    """获取 registry 中非 MCP 工具名集合（缓存）。"""
    global _builtin_names_cache
    if _builtin_names_cache is None:
        _builtin_names_cache = {
            t.name for t in registry.list_tools()
            if not t.name.startswith("mcp/")
        }
    return _builtin_names_cache


def invalidate_builtin_cache():
    """内置工具列表变化时（如动态加载 generated tools）清除缓存。"""
    global _builtin_names_cache
    _builtin_names_cache = None


class MCPToolProxy(BaseTool):
    """
    将单个 MCP Server 工具包装为 BaseTool。
    execute() 通过 MCPManager.call_tool() 发起 JSON-RPC 调用。
    """

    category = ToolCategory.CUSTOM

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        mcp_call_fn: Callable,
        *,
        registered_name: Optional[str] = None,
    ):
        super().__init__()
        self._server_name = server_name
        self._tool_name = tool_name
        self._mcp_call_fn = mcp_call_fn

        # 注册名可自定义（短名 or mcp/ 前缀）
        self.name = registered_name or f"mcp/{server_name}/{tool_name}"
        self.description = f"[MCP·{server_name}] {description}"
        self.parameters = self._convert_schema(input_schema)

    @staticmethod
    def _convert_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
        if not schema:
            return {"type": "object", "properties": {}, "required": []}
        props = {}
        for pname, pdef in schema.get("properties", {}).items():
            props[pname] = {
                "type": pdef.get("type", "string"),
                "description": pdef.get("description", ""),
            }
            if "enum" in pdef:
                props[pname]["enum"] = pdef["enum"]
        return {
            "type": "object",
            "properties": props,
            "required": schema.get("required", []),
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            result = await self._mcp_call_fn(self._server_name, self._tool_name, kwargs)
            return ToolResult(success=True, data=result)
        except Exception as e:
            logger.error("MCP tool %s/%s failed: %s", self._server_name, self._tool_name, e)
            return ToolResult(success=False, error=f"MCP 工具调用失败: {e}")


# ---------------------------------------------------------------------------
# Registry sync
# ---------------------------------------------------------------------------

def sync_mcp_tools_to_registry(registry, mcp_manager) -> List[str]:
    """
    扫描 MCPManager 中所有已连接 server 的工具，注册到 ToolRegistry。

    命名策略：
    - MCP 工具名与内置工具重叠 → 注册为 mcp/{server}/{tool}（不暴露给 LLM，
      仅供 ToolRouter fallback 使用）
    - MCP 工具名不与内置重叠 → 注册为短名 {server}_{tool}（直接暴露给 LLM）

    Returns: 新注册的工具名列表
    """
    # 先清理旧 MCP 工具
    _unregister_all_mcp_tools(registry)
    invalidate_builtin_cache()

    builtin_names = _get_builtin_names(registry)
    registered: List[str] = []

    for server_name, conn in mcp_manager._connections.items():
        if not conn.connected:
            continue
        for entry in conn.tools:
            # 判断是否与内置工具重名
            short_name = f"{server_name}_{entry.name}"
            if short_name in builtin_names or entry.name in builtin_names:
                # 重叠：用 mcp/ 前缀注册（作为 fallback）
                reg_name = f"mcp/{server_name}/{entry.name}"
            else:
                reg_name = short_name

            proxy = MCPToolProxy(
                server_name=server_name,
                tool_name=entry.name,
                description=entry.description,
                input_schema=entry.input_schema,
                mcp_call_fn=mcp_manager.call_tool,
                registered_name=reg_name,
            )
            registry.register(proxy)
            registered.append(reg_name)

    if registered:
        logger.info("Synced %d MCP tools → ToolRegistry: %s", len(registered), registered[:8])
    return registered


def _unregister_all_mcp_tools(registry) -> int:
    """移除 ToolRegistry 中所有 MCP 代理工具（mcp/ 前缀 + MCPToolProxy 实例）。"""
    mcp_names = [
        t.name for t in registry.list_tools()
        if isinstance(t, MCPToolProxy)
    ]
    for n in mcp_names:
        registry.unregister(n)
    return len(mcp_names)


def find_mcp_fallback(registry, tool_name: str) -> Optional[MCPToolProxy]:
    """
    给定一个内置工具名，查找对应的 MCP fallback 工具。
    搜索逻辑：在 mcp/ 前缀工具中找 tool_name 匹配的。
    """
    for t in registry.list_tools():
        if not isinstance(t, MCPToolProxy):
            continue
        if not t.name.startswith("mcp/"):
            continue
        # mcp/{server}/{tool} — 最后一段是原始 tool name
        parts = t.name.split("/")
        if len(parts) >= 3 and parts[-1] == tool_name:
            return t
    return None

