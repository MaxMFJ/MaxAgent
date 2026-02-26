"""
Tool Router - 统一工具执行入口
从 registry 查找工具，调用真实执行，返回 ToolResult
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional, Tuple

from .base import ToolResult
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

    try:
        result = await reg.execute(name, **args)
        return result
    except Exception as e:
        logger.exception(f"Tool {name} execute error")
        return ToolResult(success=False, error=str(e))
