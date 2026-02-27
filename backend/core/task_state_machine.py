"""
Explicit Task State Machine (v3)
为 AutonomousAgent 提供显式生命周期，便于 Debug 与可观测性。
"""
from enum import Enum
from typing import Optional, Callable, List
import logging

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    REFLECTING = "reflecting"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ABORTED = "aborted"

    def is_terminal(self) -> bool:
        return self in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.TIMEOUT,
            TaskState.ABORTED,
        )


# 合法迁移（from -> to）
VALID_TRANSITIONS = {
    (TaskState.PENDING, TaskState.RUNNING),
    (TaskState.PENDING, TaskState.FAILED),
    (TaskState.PENDING, TaskState.ABORTED),
    (TaskState.RUNNING, TaskState.WAITING_TOOL),
    (TaskState.RUNNING, TaskState.REFLECTING),
    (TaskState.RUNNING, TaskState.RETRYING),
    (TaskState.RUNNING, TaskState.COMPLETED),
    (TaskState.RUNNING, TaskState.FAILED),
    (TaskState.RUNNING, TaskState.TIMEOUT),
    (TaskState.RUNNING, TaskState.ABORTED),
    (TaskState.WAITING_TOOL, TaskState.RUNNING),
    (TaskState.WAITING_TOOL, TaskState.FAILED),
    (TaskState.WAITING_TOOL, TaskState.RETRYING),
    (TaskState.REFLECTING, TaskState.RUNNING),
    (TaskState.REFLECTING, TaskState.COMPLETED),
    (TaskState.RETRYING, TaskState.RUNNING),
    (TaskState.RETRYING, TaskState.FAILED),
}


class TaskStateMachine:
    """
    任务状态机。AutonomousAgent 在关键节点调用 transition() 更新状态。
    """

    def __init__(self, task_id: str, on_transition: Optional[Callable[[TaskState, TaskState], None]] = None):
        self.task_id = task_id
        self._state = TaskState.PENDING
        self._on_transition = on_transition
        self._history: List[TaskState] = [TaskState.PENDING]

    @property
    def state(self) -> TaskState:
        return self._state

    def transition(self, to: TaskState) -> bool:
        """迁移到 to；若非法则返回 False 并打日志。"""
        from_state = self._state
        if (from_state, to) not in VALID_TRANSITIONS and from_state != to:
            logger.warning(
                "TaskStateMachine invalid transition: %s -> %s (task_id=%s)",
                from_state.value, to.value, self.task_id,
            )
            return False
        if from_state == to:
            return True
        self._state = to
        self._history.append(to)
        if self._on_transition:
            try:
                self._on_transition(from_state, to)
            except Exception as e:
                logger.debug("on_transition callback error: %s", e)
        logger.debug("TaskStateMachine %s: %s -> %s", self.task_id, from_state.value, to.value)
        return True

    def is_done(self) -> bool:
        return self._state.is_terminal()

    def history(self) -> List[TaskState]:
        return list(self._history)
