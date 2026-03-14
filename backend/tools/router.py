"""
Tool Router - 统一工具执行入口（Unified Tool Router）
从 registry 查找工具 → 执行 → 内置失败时自动 fallback 到 MCP Adapter
v3: 工具执行通过 TimeoutPolicy.with_tool_timeout 包装。

优先级：Builtin Tool → MCP Adapter（同名工具内置优先，失败后 fallback）
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional, Tuple

from .base import ToolResult

try:
    from core.timeout_policy import get_timeout_policy
except ImportError:
    get_timeout_policy = None
from .middleware import run_pre_hooks, run_post_hooks
from .registry import ToolRegistry
from .validator import validate_tool_call

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)

# 全局 registry 由 Agent 注入
_router_registry: Optional[ToolRegistry] = None


def set_router_registry(registry: ToolRegistry) -> None:
    """注入 ToolRegistry 供 router 使用"""
    global _router_registry
    _router_registry = registry


# 工具别名：Capsule/技能中使用的名称 -> 实际注册的工具名及参数映射
# 例如 capsule_system_health_check 使用 tool "system"、args {"action":"info"}，实际工具为 system_info
def _system_args_map(a: dict) -> dict:
    if not a:
        return {"info_type": "overview"}
    if "info_type" in a:
        return a
    if a.get("action") == "info":
        return {"info_type": "overview"}
    return {"info_type": a.get("info_type", "overview")}


TOOL_ALIASES = {
    "system": {"target": "system_info", "args_map": _system_args_map},
}


def _normalize_tool_name_and_args(name: str, args: dict) -> Tuple[str, dict]:
    """将别名工具名和胶囊风格参数映射为实际工具名与参数。"""
    if name not in TOOL_ALIASES:
        return name, args or {}
    alias = TOOL_ALIASES[name]
    target_name = alias["target"]
    args = dict(args or {})
    if "args_map" in alias and callable(alias["args_map"]):
        args = alias["args_map"](args)
    return target_name, args


async def execute_tool(
    name: str,
    args: dict,
    registry: Optional[ToolRegistry] = None,
    bind_target_fn=None,
) -> ToolResult:
    """
    执行工具调用
    
    Args:
        name: 工具名
        args: 参数字典
        registry: 可选，不传则使用全局注入的 registry
        bind_target_fn: 可选，用于绑定 current_task.target 到 args
    
    Returns:
        ToolResult(success, result/error)
    """
    reg = registry or _router_registry
    if not reg:
        return ToolResult(success=False, error="ToolRegistry 未初始化")

    # 别名与参数映射（如 capsule 使用 "system" + {"action":"info"} -> system_info + {"info_type":"overview"}）
    name, args = _normalize_tool_name_and_args(name, args or {})

    # 校验
    valid, err = validate_tool_call(name, args)
    if not valid:
        return ToolResult(success=False, error=err or "参数校验失败")

    # 可选：绑定 task target
    if bind_target_fn and callable(bind_target_fn):
        args = dict(args)
        args = bind_target_fn(name, args)

    # 预执行中间件（可修改 args，如限流、参数补全）
    args = await run_pre_hooks(name, args)

    try:
        execute_coro = reg.execute(name, **args)
        if get_timeout_policy is not None:
            result = await get_timeout_policy().with_tool_timeout(execute_coro)
        else:
            result = await execute_coro
        # 后执行中间件（可修改 result，如截断、格式化、埋点）
        result = await run_post_hooks(name, args, result)

        # ── MCP Fallback ──────────────────────────────────────────────
        # 内置工具返回 tool_not_found 或执行失败时，尝试 MCP 同名工具
        if not result.success:
            mcp_proxy = _try_mcp_fallback(reg, name)
            if mcp_proxy is not None:
                logger.info("Builtin tool '%s' failed, falling back to MCP: %s", name, mcp_proxy.name)
                try:
                    mcp_coro = mcp_proxy.execute(**args)
                    if get_timeout_policy is not None:
                        result = await get_timeout_policy().with_tool_timeout(mcp_coro)
                    else:
                        result = await mcp_coro
                    result = await run_post_hooks(name, args, result)
                except Exception as mcp_err:
                    logger.warning("MCP fallback for '%s' also failed: %s", name, mcp_err)

        # ── MCP Catalog Auto-Suggest ────────────────────────────────
        # 工具完全不存在且无 MCP fallback 时，自动搜索 MCP Catalog 推荐安装
        if not result.success and isinstance(result.data, dict) and result.data.get("tool_not_found"):
            result = _enrich_with_catalog_suggestions(result, name)

        return result
    except asyncio.TimeoutError as e:
        logger.warning(f"Tool {name} timed out: {e}")
        return ToolResult(success=False, error=f"工具执行超时: {e}")
    except Exception as e:
        logger.exception(f"Tool {name} execute error")
        return ToolResult(success=False, error=str(e))


def _try_mcp_fallback(reg: ToolRegistry, tool_name: str):
    """尝试查找 MCP fallback 工具（延迟导入避免循环依赖）。"""
    try:
        from .mcp_adapter import find_mcp_fallback
        return find_mcp_fallback(reg, tool_name)
    except ImportError:
        return None


def _enrich_with_catalog_suggestions(result: ToolResult, tool_name: str) -> ToolResult:
    """当工具不存在时，搜索 MCP Catalog 并在错误信息中推荐可安装的 MCP 服务。"""
    try:
        from services.mcp_catalog_service import get_mcp_catalog
        catalog = get_mcp_catalog()
        matches = catalog.search(tool_name, limit=3)
        if not matches:
            return result
        suggestions = []
        for entry in matches:
            suggestions.append(f"- {entry.name} (id={entry.id}): {entry.description}")
        hint = (
            f"\n\n💡 在 MCP Catalog 中发现以下可能匹配的服务，"
            f"你可以调用 request_mcp_install 工具来安装：\n"
            + "\n".join(suggestions)
        )
        return ToolResult(
            success=False,
            error=(result.error or "") + hint,
            data=result.data,
        )
    except Exception as e:
        logger.debug("MCP catalog suggestion failed: %s", e)
        return result
