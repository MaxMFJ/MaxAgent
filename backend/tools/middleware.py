"""
工具执行中间件：在执行前后插入可插拔逻辑（校验、限流、日志、结果格式化等）。
不改变 BaseTool / Registry 实现，由 router.execute_tool 统一调用。
"""

import asyncio
import logging
from typing import Any, Callable, List

from .base import ToolResult

logger = logging.getLogger(__name__)

# 预执行钩子: (name, args) -> 可选修改后的 args，返回 None 表示不修改
# 后执行钩子: (name, args, result) -> 可选修改后的 result，返回 None 表示不修改
_PreHook = Callable[[str, dict], Any]  # async, return Optional[dict]
_PostHook = Callable[[str, dict, ToolResult], Any]  # async, return Optional[ToolResult]

_pre_hooks: List[Any] = []
_post_hooks: List[Any] = []


def register_pre_hook(hook: _PreHook) -> None:
    """注册工具执行前钩子（如校验、限流、参数补全）。hook 为 async (name, args) -> args 或 None"""
    _pre_hooks.append(hook)


def register_post_hook(hook: _PostHook) -> None:
    """注册工具执行后钩子（如结果截断、格式化、埋点）。hook 为 async (name, args, result) -> result 或 None"""
    _post_hooks.append(hook)


def get_pre_hooks() -> List[Any]:
    return list(_pre_hooks)


def get_post_hooks() -> List[Any]:
    return list(_post_hooks)


async def run_pre_hooks(name: str, args: dict) -> dict:
    """依次执行预执行钩子；若某钩子返回非 None，则用其作为新的 args 继续后续钩子及执行。"""
    current = dict(args or {})
    for h in _pre_hooks:
        try:
            out = await h(name, current) if asyncio.iscoroutinefunction(h) else h(name, current)
            if out is not None and isinstance(out, dict):
                current = out
        except Exception as e:
            logger.warning("Tool pre-hook %s error: %s", getattr(h, "__name__", h), e)
    return current


async def run_post_hooks(name: str, args: dict, result: ToolResult) -> ToolResult:
    """依次执行后执行钩子；若某钩子返回非 None，则用其作为新的 result 继续后续钩子。"""
    current = result
    for h in _post_hooks:
        try:
            out = await h(name, args, current) if asyncio.iscoroutinefunction(h) else h(name, args, current)
            if out is not None and isinstance(out, ToolResult):
                current = out
        except Exception as e:
            logger.warning("Tool post-hook %s error: %s", getattr(h, "__name__", h), e)
    return current


