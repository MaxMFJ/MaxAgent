"""
Duck Status Tool — 查询 Duck 分身 Agent 状态

供 LLM 在委派任务前查询当前在线的 Duck 分身，判断是否有可用分身、类型分布等。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import BaseTool, ToolResult, ToolCategory

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)


class DuckStatusTool(BaseTool):
    """
    查询 Chow Duck 分身 Agent 的当前状态。
    在委派任务前可先调用此工具，确认是否有在线 Duck、类型分布、是否忙碌等。
    """

    name = "duck_status"
    description = (
        "查询 Duck 分身 Agent 状态。返回所有已注册 Duck 的在线/忙碌/离线情况、类型、名称等。"
        "【重要】仅在委派任务前调用一次，用于确认可用 Duck。"
        "委派 delegate_duck 后禁止反复调用此工具轮询进度——任务完成后系统会自动推送通知。"
    )
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "duck_type": {
                "type": "string",
                "description": "可选，按类型过滤：coder/designer/crawler/image/video/tester/general",
                "enum": ["coder", "designer", "crawler", "image", "video", "tester", "general"],
            },
        },
        "required": [],
    }

    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        super().__init__(runtime_adapter)

    async def execute(self, **kwargs) -> ToolResult:
        duck_type_filter = kwargs.get("duck_type")

        try:
            from app_state import IS_DUCK_MODE
            if IS_DUCK_MODE:
                return ToolResult(success=False, error="Duck 模式下无法查询主 Duck 列表")

            from services.duck_registry import DuckRegistry
            from services.duck_protocol import DuckStatus, DuckType

            registry = DuckRegistry.get_instance()
            await registry.initialize()

            all_ducks = await registry.list_all()
            if duck_type_filter:
                try:
                    dt = DuckType(duck_type_filter)
                    all_ducks = [d for d in all_ducks if d.duck_type == dt]
                except ValueError:
                    pass

            online = [d for d in all_ducks if d.status == DuckStatus.ONLINE]
            busy = [d for d in all_ducks if d.status == DuckStatus.BUSY]
            offline = [d for d in all_ducks if d.status == DuckStatus.OFFLINE]

            def _duck_summary(d) -> Dict[str, Any]:
                return {
                    "duck_id": d.duck_id,
                    "name": d.name,
                    "duck_type": d.duck_type.value,
                    "status": d.status.value,
                    "is_local": d.is_local,
                    "current_task_id": d.current_task_id,
                    "completed_tasks": d.completed_tasks,
                    "failed_tasks": d.failed_tasks,
                }

            summary = {
                "total": len(all_ducks),
                "online": len(online),
                "busy": len(busy),
                "offline": len(offline),
                "available_for_delegate": len(online),  # 空闲可接任务的 Duck 数
                "ducks": [_duck_summary(d) for d in all_ducks],
                "_reminder": (
                    "⚠️ 查询完成。如果你即将调用 delegate_duck，调用后请勿反复轮询本工具检查进度。"
                    "系统采用推送机制，任务完成后会自动发送 [系统自动续步] 通知。"
                    "委派后直接结束本轮回复，等待系统通知即可。"
                ),
            }

            return ToolResult(success=True, data=summary)
        except ImportError as e:
            logger.warning("Duck status dependencies not available: %s", e)
            return ToolResult(success=False, error="Duck 注册中心不可用")
        except Exception as e:
            logger.exception("duck_status tool error")
            return ToolResult(success=False, error=f"查询失败: {e}")
