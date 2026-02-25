"""
Capsule Tool - Agent 调用本地技能 Capsule（格式兼容 EvoMap，无需官方库）
支持列出、查询、执行、重载、同步、统计本地/缓存中的 Capsule。
"""

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import BaseTool, ToolResult, ToolCategory

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)


class CapsuleTool(BaseTool):
    """
    本地技能 Capsule：列出、按任务查找、按 id 获取、执行、重载、同步、统计。
    来源为 backend/capsules/ 与可选 GitHub 源，无需 EvoMap 官方库或账号。
    """

    name = "capsule"
    description = (
        "使用本地技能 Capsule：列出已加载的 Capsule、按任务查找、按 id 获取、执行、"
        "重载、从 GitHub 同步、查看统计。来源为本地目录与可选配置的仓库，无需 EvoMap 官方库。"
    )
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "操作: list(列出全部), find(按任务关键词查找), get(按id获取), "
                    "execute(执行), reload(热重载), sync(从GitHub同步), stats(统计信息)"
                ),
                "enum": ["list", "find", "get", "execute", "reload", "sync", "stats"],
            },
            "task": {
                "type": "string",
                "description": "任务关键词，find 时使用，如 screenshot、打开应用",
            },
            "capsule_id": {
                "type": "string",
                "description": "Capsule 的 id，get 或 execute 时使用",
            },
            "inputs": {
                "type": "object",
                "description": "执行 Capsule 时的输入参数，execute 时使用",
            },
            "source_url": {
                "type": "string",
                "description": "sync 时可指定额外的 GitHub URL 来源",
            },
        },
        "required": ["action"],
    }

    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        super().__init__(runtime_adapter)

    async def execute(self, **kwargs) -> ToolResult:
        action = (kwargs.get("action") or "").strip().lower()
        if not action:
            return ToolResult(success=False, error="action is required")

        try:
            if action == "list":
                return await self._handle_list()
            elif action == "find":
                return await self._handle_find(kwargs)
            elif action == "get":
                return await self._handle_get(kwargs)
            elif action == "execute":
                return await self._handle_execute(kwargs)
            elif action == "reload":
                return await self._handle_reload()
            elif action == "sync":
                return await self._handle_sync(kwargs)
            elif action == "stats":
                return await self._handle_stats()
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.exception("Capsule tool error")
            return ToolResult(success=False, error=str(e))

    async def _handle_list(self) -> ToolResult:
        from agent.capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        caps = registry.list_capsules()
        data = [c.to_summary() for c in caps]
        return ToolResult(success=True, data={"count": len(data), "capsules": data})

    async def _handle_find(self, kwargs) -> ToolResult:
        from agent.capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        task = kwargs.get("task", "")
        if not task:
            return ToolResult(success=False, error="task is required for find")
        caps = registry.find_capsule_by_task(task, limit=10)
        data = [c.to_summary() for c in caps]
        return ToolResult(success=True, data={"count": len(data), "capsules": data})

    async def _handle_get(self, kwargs) -> ToolResult:
        from agent.capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        cid = kwargs.get("capsule_id", "")
        if not cid:
            return ToolResult(success=False, error="capsule_id is required for get")
        cap = registry.get_capsule(cid)
        if not cap:
            return ToolResult(success=False, error=f"Capsule not found: {cid}")
        return ToolResult(success=True, data=cap.to_dict())

    async def _handle_execute(self, kwargs) -> ToolResult:
        from agent.capsule_registry import get_capsule_registry
        from agent.capsule_executor import execute_capsule
        registry = get_capsule_registry()
        cid = kwargs.get("capsule_id", "")
        inputs = kwargs.get("inputs")
        if not cid:
            return ToolResult(success=False, error="capsule_id is required for execute")
        cap = registry.get_capsule(cid)
        if not cap:
            return ToolResult(success=False, error=f"Capsule not found: {cid}")
        if inputs is None:
            inputs = {}
        if not isinstance(inputs, dict):
            inputs = {}
        result = await execute_capsule(cap, inputs)
        registry.record_execution(cid, success=result.get("success", False))

        outputs = result.get("outputs", {})
        if outputs.get("instruction_mode"):
            return ToolResult(
                success=True,
                data={
                    "instruction_mode": True,
                    "capsule_id": cid,
                    "instructions": outputs.get("instructions", ""),
                    "message": (
                        f"技能 '{cap.description}' 已激活。这是一个指令型技能，"
                        "请按照 instructions 中的步骤，使用你已有的工具逐步执行。"
                    ),
                },
            )

        return ToolResult(
            success=result.get("success", False),
            data=result,
            error=result.get("error"),
        )

    async def _handle_reload(self) -> ToolResult:
        from agent.capsule_bootstrap import reload_capsules
        result = await reload_capsules(run_sync=False)
        return ToolResult(success=True, data=result)

    async def _handle_sync(self, kwargs) -> ToolResult:
        from agent.capsule_bootstrap import reload_capsules
        from agent.capsule_sync import sync_capsules_from_sources

        source_url = kwargs.get("source_url", "")
        extra_sources = [source_url] if source_url else None

        sync_result = await sync_capsules_from_sources(sources=extra_sources)
        reload_result = await reload_capsules(run_sync=False)

        return ToolResult(success=True, data={
            "sync": sync_result,
            "reload": reload_result,
        })

    async def _handle_stats(self) -> ToolResult:
        from agent.capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        stats = registry.get_stats()
        return ToolResult(success=True, data=stats)
