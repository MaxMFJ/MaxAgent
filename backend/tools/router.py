"""
Tool Router - 统一工具执行入口
从 registry 查找工具，调用真实执行，返回 ToolResult
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

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
