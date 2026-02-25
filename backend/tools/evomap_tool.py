"""
EvoMap Tool - Allows the agent to interact with the EvoMap evolution network.
Supports searching for capabilities, inheriting strategies, and publishing results.
"""

import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import BaseTool, ToolResult, ToolCategory

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)


class EvoMapTool(BaseTool):
    """
    Tool for interacting with the EvoMap GEP evolution network.
    Enables the agent to search for proven strategies, inherit capsules,
    publish its own capabilities, and check network status.
    """

    name = "evomap"
    description = (
        "与 EvoMap 进化网络交互：搜索已验证的 AI 能力策略（Capsule/Gene），"
        "继承其他 Agent 的策略，发布自己的成功策略，查看网络状态。"
        "当遇到新任务或需要策略参考时优先使用。"
    )
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: search(搜索能力), inherit(继承策略), publish(发布能力), status(查看状态), resolve(解析任务策略)",
                "enum": ["search", "inherit", "publish", "status", "resolve"],
            },
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "信号/关键词列表，用于搜索匹配的策略 (search/resolve 时使用)",
            },
            "task": {
                "type": "string",
                "description": "任务描述，用于 resolve 操作自动提取信号并匹配策略",
            },
            "capsule_data": {
                "type": "object",
                "description": "要继承的 Capsule 数据 (inherit 时使用)",
            },
            "tool_name": {
                "type": "string",
                "description": "发布能力时的工具名称 (publish 时使用)",
            },
            "strategy": {
                "type": "array",
                "items": {"type": "string"},
                "description": "策略步骤列表 (publish 时使用)",
            },
            "summary": {
                "type": "string",
                "description": "能力描述摘要 (publish 时使用)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        super().__init__(runtime_adapter)

    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        try:
            from agent.evomap_service import get_evomap_service
            service = get_evomap_service()
        except Exception as e:
            return ToolResult(success=False, error=f"EvoMap service unavailable: {e}")

        try:
            if action == "search":
                return await self._handle_search(service, kwargs)
            elif action == "inherit":
                return await self._handle_inherit(service, kwargs)
            elif action == "publish":
                return await self._handle_publish(service, kwargs)
            elif action == "status":
                return await self._handle_status(service)
            elif action == "resolve":
                return await self._handle_resolve(service, kwargs)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"EvoMap tool error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    async def _handle_search(self, service, kwargs) -> ToolResult:
        signals = kwargs.get("signals", [])
        if not signals:
            return ToolResult(success=False, error="signals parameter required for search")
        result = await service.client.search_capsules(signals, limit=10)
        return ToolResult(success=True, data=result)

    async def _handle_inherit(self, service, kwargs) -> ToolResult:
        capsule_data = kwargs.get("capsule_data")
        if not capsule_data:
            return ToolResult(success=False, error="capsule_data required for inherit")
        result = await service.client.inherit_capsule(capsule_data)
        return ToolResult(success=True, data=result)

    async def _handle_publish(self, service, kwargs) -> ToolResult:
        tool_name = kwargs.get("tool_name", "")
        strategy = kwargs.get("strategy", [])
        signals = kwargs.get("signals", [])
        summary = kwargs.get("summary", "")
        if not tool_name or not strategy:
            return ToolResult(success=False, error="tool_name and strategy required for publish")
        result = await service.publish_capability(
            tool_name=tool_name,
            strategy=strategy,
            signals=signals or [tool_name],
            summary=summary,
        )
        return ToolResult(success=True, data=result)

    async def _handle_status(self, service) -> ToolResult:
        status = service.get_status()
        return ToolResult(success=True, data=status)

    async def _handle_resolve(self, service, kwargs) -> ToolResult:
        task = kwargs.get("task", "")
        signals = kwargs.get("signals")
        if not task and not signals:
            return ToolResult(success=False, error="task or signals required for resolve")
        result = await service.resolve_capability(task, signals)
        return ToolResult(success=True, data=result)
