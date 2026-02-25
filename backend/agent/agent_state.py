"""
Agent State - 会话级 Agent 状态
存储 current_task，配合 context_manager 的 session_context 使用
"""

import logging
from typing import Dict, Optional

from .task_context_manager import TaskContext

logger = logging.getLogger(__name__)

# 每会话的 current_task，session_id -> TaskContext
_session_current_task: Dict[str, Optional[TaskContext]] = {}


def get_current_task(session_id: str) -> Optional[TaskContext]:
    """获取当前会话的任务上下文"""
    return _session_current_task.get(session_id)


def set_current_task(session_id: str, task: Optional[TaskContext]) -> None:
    """设置当前会话的任务上下文"""
    _session_current_task[session_id] = task
    if task:
        logger.debug(f"Session {session_id}: current_task = {task.task_type}, target = {task.target}")
    else:
        logger.debug(f"Session {session_id}: current_task cleared")


def clear_current_task(session_id: str) -> None:
    """清除当前任务"""
    set_current_task(session_id, None)
