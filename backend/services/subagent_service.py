"""
Subagent 子 Agent 并行执行服务
将复杂任务拆分给多个轻量子 Agent 并行处理，结果聚合回主任务。
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from services.audit_service import append_audit_event

logger = logging.getLogger(__name__)


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Subtask:
    subtask_id: str
    parent_task_id: str
    description: str
    status: SubtaskStatus = SubtaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    execution_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "parent_task_id": self.parent_task_id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "execution_time_ms": self.execution_time_ms,
        }


class SubagentScheduler:
    """任务拆分与子 Agent 调度"""

    def __init__(self):
        self._active_subtasks: Dict[str, List[Subtask]] = {}  # parent_task_id -> subtasks

    async def split_task(self, task_description: str, llm_client: Any = None) -> List[str]:
        """
        使用 LLM 将任务拆分为子任务。
        返回子任务描述列表。如果 LLM 不可用或任务不需拆分，返回空列表。
        """
        import app_state
        if not getattr(app_state, "ENABLE_SUBAGENT", False):
            return []

        if llm_client is None:
            return []

        try:
            response = await llm_client.chat.completions.create(
                model=llm_client._model if hasattr(llm_client, "_model") else "gpt-4",
                messages=[{
                    "role": "user",
                    "content": (
                        f"将以下任务拆分为可独立并行执行的子任务（2-4个），每行一个子任务描述。\n"
                        f"如果任务不需要拆分，回复「不需要拆分」。\n\n"
                        f"任务: {task_description}"
                    ),
                }],
                temperature=0.3,
                max_tokens=500,
            )
            text = response.choices[0].message.content.strip()
            if "不需要拆分" in text:
                return []
            subtasks = [line.strip().lstrip("0123456789.-) ") for line in text.split("\n") if line.strip()]
            max_concurrent = getattr(app_state, "SUBAGENT_MAX_CONCURRENT", 3)
            return subtasks[:max_concurrent]
        except Exception as e:
            logger.warning("Task split failed: %s", e)
            return []

    async def execute_subtasks(
        self,
        parent_task_id: str,
        session_id: str,
        subtask_descriptions: List[str],
        execute_fn: Any = None,
    ) -> List[Subtask]:
        """
        并行执行子任务。
        execute_fn: async (description: str) -> (success: bool, output: str, error: str)
        """
        import app_state
        timeout = getattr(app_state, "SUBAGENT_TIMEOUT", 300)

        subtasks = []
        for desc in subtask_descriptions:
            st = Subtask(
                subtask_id=uuid.uuid4().hex[:12],
                parent_task_id=parent_task_id,
                description=desc,
            )
            subtasks.append(st)

        self._active_subtasks[parent_task_id] = subtasks

        if execute_fn is None:
            for st in subtasks:
                st.status = SubtaskStatus.ERROR
                st.error = "No execute function provided"
            return subtasks

        append_audit_event(
            "action_execute",
            task_id=parent_task_id,
            session_id=session_id,
            action_type="subagent_dispatch",
            params_summary=f"Dispatching {len(subtasks)} subtasks",
            result="started",
            details={"subtask_count": len(subtasks)},
        )

        async def _run_one(st: Subtask):
            st.status = SubtaskStatus.RUNNING
            start = time.time()
            try:
                success, output, error = await asyncio.wait_for(
                    execute_fn(st.description), timeout=timeout
                )
                st.execution_time_ms = int((time.time() - start) * 1000)
                st.finished_at = time.time()
                if success:
                    st.status = SubtaskStatus.COMPLETED
                    st.result = output
                else:
                    st.status = SubtaskStatus.ERROR
                    st.error = error
            except asyncio.TimeoutError:
                st.execution_time_ms = int((time.time() - start) * 1000)
                st.finished_at = time.time()
                st.status = SubtaskStatus.TIMEOUT
                st.error = f"Subtask timed out after {timeout}s"
            except Exception as e:
                st.execution_time_ms = int((time.time() - start) * 1000)
                st.finished_at = time.time()
                st.status = SubtaskStatus.ERROR
                st.error = str(e)

        await asyncio.gather(*[_run_one(st) for st in subtasks])

        self._active_subtasks.pop(parent_task_id, None)
        return subtasks

    def get_active_subtasks(self, parent_task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """查看活跃的子任务"""
        if parent_task_id:
            return [st.to_dict() for st in self._active_subtasks.get(parent_task_id, [])]
        result = []
        for subtasks in self._active_subtasks.values():
            result.extend([st.to_dict() for st in subtasks])
        return result


# 全局单例
_scheduler: Optional[SubagentScheduler] = None


def get_subagent_scheduler() -> SubagentScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = SubagentScheduler()
    return _scheduler
