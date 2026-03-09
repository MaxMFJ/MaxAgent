"""
Delegate Duck Tool — 委派子任务给 Duck 分身 Agent

供 Chat 模式（工具调用）使用，当有在线 Duck 时可将任务委派给分身执行。
采用异步模式：提交后立即返回，子 Duck 完成后通过 duck_task_complete 主动通知用户。
"""

import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import BaseTool, ToolResult, ToolCategory

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)


class DelegateDuckTool(BaseTool):
    """
    委派子任务给 Chow Duck 分身 Agent。
    当有在线 Duck 时，可将代码编写、网页制作、爬虫、设计等任务委派给分身执行。
    若无可用 Duck 会返回错误，主 Agent 应自行完成。
    """

    name = "delegate_duck"
    description = (
        "委派子任务给 Duck 分身 Agent。当有在线 Duck 时，可将代码编写、网页制作、爬虫、设计等任务委派给分身执行。"
        "提交后立即返回，子 Duck 完成后会主动通知用户。"
        "参数：description(必填，任务描述)、duck_type(可选，coder/designer/crawler/general)。"
        "若无可用 Duck 会返回错误，请自行用 file_operations 或 terminal 完成。"
    )
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "要委派给 Duck 的子任务描述，如「制作一个简单的 HTML 页面保存到桌面」",
            },
            "duck_type": {
                "type": "string",
                "description": "Duck 类型，可选：coder(编程)、designer(设计)、crawler(爬虫)、general(通用)",
                "enum": ["coder", "designer", "crawler", "image", "video", "tester", "general"],
            },
        },
        "required": ["description"],
    }

    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        super().__init__(runtime_adapter)

    async def execute(self, **kwargs) -> ToolResult:
        description = (kwargs.get("description") or "").strip()
        if not description:
            return ToolResult(success=False, error="description 必填")

        try:
            from app_state import IS_DUCK_MODE
            if IS_DUCK_MODE:
                return ToolResult(success=False, error="Duck 模式下不允许再次委派子任务")

            from services.duck_task_scheduler import get_task_scheduler
            from services.duck_protocol import DuckType, TaskStatus

            # ── 串行保护：同一会话如果已有活跃 Duck 任务，拒绝新的委派 ──
            from agent.terminal_session import get_current_session_id as _get_sid
            _cur_session = _get_sid() or "default"
            scheduler_pre = get_task_scheduler()
            for _tid, _sid in list(scheduler_pre._task_sessions.items()):
                if _sid == _cur_session:
                    _t = scheduler_pre._tasks.get(_tid)
                    if _t and _t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
                        return ToolResult(
                            success=False,
                            error=(
                                f"当前会话已有活跃 Duck 任务（{_t.task_id[:8]}…），请等待其完成后再委派新任务。"
                                "Duck 完成后系统会自动通知你，届时可继续委派下一步。"
                            ),
                        )

            duck_type = kwargs.get("duck_type")
            dt = None
            if duck_type:
                try:
                    dt = DuckType(duck_type)
                except ValueError:
                    pass

            # 注入实际路径，避免 Duck 用 xxx/$(whoami) 等占位符
            desktop_path = os.path.realpath(os.path.expanduser("~/Desktop"))
            enhanced_description = (
                f"{description}\n\n"
                f"【重要】保存文件时必须使用实际路径：{desktop_path}，禁止用 /Users/xxx/ 或 $(whoami)。"
            )

            from agent.terminal_session import get_current_session_id

            scheduler = get_task_scheduler()
            await scheduler.initialize()

            # 异步模式：提交后立即返回，不等待子 Duck 完成。子 Duck 完成后通过 duck_task_complete 主动通知用户。
            source_session_id = get_current_session_id() or "default"
            task = await scheduler.submit(
                description=enhanced_description,
                task_type="general",
                params={},
                priority=0,
                timeout=1800,
                strategy="single",
                target_duck_id=None,
                target_duck_type=dt,
                source_session_id=source_session_id,
            )

            if task.status == TaskStatus.PENDING:
                return ToolResult(
                    success=False,
                    error="无可用 Duck 处理此任务，任务已排队。请自行用 file_operations 或 terminal 完成。",
                    data={"task_id": task.task_id},
                )

            # 已分配 Duck，立即返回成功。主 Agent 本轮结束，等待 Duck 完成时由系统触发续步
            duck_type_label = dt.value if dt else "通用"
            desktop_path = os.path.realpath(os.path.expanduser("~/Desktop"))
            return ToolResult(
                success=True,
                data={
                    "task_id": task.task_id,
                    "duck_id": task.assigned_duck_id,
                    "duck_type": duck_type_label,
                    "message": f"任务已委派给 {duck_type_label} Duck，完成后会主动通知你。请稍候。",
                    "actual_desktop_path": desktop_path,
                },
            )
        except ImportError as e:
            logger.warning("Delegate duck dependencies not available: %s", e)
            return ToolResult(success=False, error="Duck 调度器不可用，请自行完成")
        except Exception as e:
            logger.exception("delegate_duck tool error")
            return ToolResult(success=False, error=f"委派失败: {e}")
