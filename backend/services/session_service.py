"""
Session Resume / Fork 服务
基于 TaskPersistenceManager 扩展跨会话的持久化、恢复和分支功能。
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from task_persistence import (
    TaskPersistenceManager,
    TaskCheckpoint,
    PersistentTaskStatus,
    CHECKPOINT_DIR,
)
from services.audit_service import append_audit_event

logger = logging.getLogger(__name__)


class SessionService:
    """会话持久化与恢复服务"""

    def __init__(self, persistence: TaskPersistenceManager):
        self._persistence = persistence

    async def list_resumable_sessions(self) -> List[Dict[str, Any]]:
        """列出所有可恢复的会话（有检查点且未运行中）"""
        import app_state
        if not getattr(app_state, "ENABLE_SESSION_RESUME", False):
            return []

        await self._persistence.initialize()
        sessions: Dict[str, Dict[str, Any]] = {}

        for fpath in CHECKPOINT_DIR.glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sid = data.get("session_id", "")
                status = data.get("status", "")
                if status == PersistentTaskStatus.RUNNING.value:
                    continue
                if sid not in sessions or data.get("updated_at", "") > sessions[sid].get("updated_at", ""):
                    sessions[sid] = {
                        "session_id": sid,
                        "task_id": data.get("task_id", ""),
                        "task_description": data.get("task_description", ""),
                        "status": status,
                        "current_iteration": data.get("current_iteration", 0),
                        "max_iterations": data.get("max_iterations", 50),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "checkpoint_count": data.get("current_iteration", 0),
                    }
            except Exception:
                continue
        return list(sessions.values())

    async def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """列出指定会话的所有检查点"""
        import app_state
        if not getattr(app_state, "ENABLE_SESSION_RESUME", False):
            return []

        results = []
        for fpath in CHECKPOINT_DIR.glob("*.json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("session_id") != session_id:
                    continue
                results.append({
                    "task_id": data.get("task_id", ""),
                    "session_id": session_id,
                    "status": data.get("status", ""),
                    "current_iteration": data.get("current_iteration", 0),
                    "max_iterations": data.get("max_iterations", 50),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "action_count": len(data.get("action_checkpoints", [])),
                    "final_result": data.get("final_result"),
                })
            except Exception:
                continue
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results

    async def resume_session(self, session_id: str, checkpoint_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        恢复会话执行准备。返回恢复所需的 checkpoint 数据。
        实际恢复执行由 AutonomousAgent 完成。
        """
        import app_state
        if not getattr(app_state, "ENABLE_SESSION_RESUME", False):
            return None

        if checkpoint_id:
            checkpoint = await self._persistence.load_checkpoint(checkpoint_id)
        else:
            checkpoint = await self._persistence.load_checkpoint_by_session(session_id)

        if checkpoint is None:
            return None

        append_audit_event(
            "session_start",
            task_id=checkpoint.task_id,
            session_id=session_id,
            result="resume",
            details={"from_iteration": checkpoint.current_iteration},
        )

        return {
            "task_id": checkpoint.task_id,
            "session_id": checkpoint.session_id,
            "task_description": checkpoint.task_description,
            "current_iteration": checkpoint.current_iteration,
            "max_iterations": checkpoint.max_iterations,
            "status": checkpoint.status.value if isinstance(checkpoint.status, PersistentTaskStatus) else checkpoint.status,
            "action_count": len(checkpoint.action_checkpoints),
            "can_resume": checkpoint.status in (
                PersistentTaskStatus.STOPPED,
                PersistentTaskStatus.ERROR,
                PersistentTaskStatus.PAUSED,
                PersistentTaskStatus.ORPHAN_TIMEOUT,
            ),
        }

    async def fork_session(self, session_id: str, checkpoint_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        从检查点分支创建新会话。
        深拷贝 checkpoint，生成新 session_id 和 task_id。
        """
        import app_state
        if not getattr(app_state, "ENABLE_SESSION_RESUME", False):
            return None

        if checkpoint_id:
            checkpoint = await self._persistence.load_checkpoint(checkpoint_id)
        else:
            checkpoint = await self._persistence.load_checkpoint_by_session(session_id)

        if checkpoint is None:
            return None

        new_session_id = uuid.uuid4().hex[:12]
        new_task_id = uuid.uuid4().hex[:16]

        forked = TaskCheckpoint(
            task_id=new_task_id,
            session_id=new_session_id,
            task_description=checkpoint.task_description,
            status=PersistentTaskStatus.PAUSED,
            current_iteration=checkpoint.current_iteration,
            max_iterations=checkpoint.max_iterations,
            action_checkpoints=list(checkpoint.action_checkpoints),
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            final_result=None,
        )
        await self._persistence.save_checkpoint(forked)

        append_audit_event(
            "session_start",
            task_id=new_task_id,
            session_id=new_session_id,
            result="fork",
            details={
                "fork_parent_session": session_id,
                "fork_parent_task": checkpoint.task_id,
                "from_iteration": checkpoint.current_iteration,
            },
        )

        return {
            "new_session_id": new_session_id,
            "new_task_id": new_task_id,
            "parent_session_id": session_id,
            "parent_task_id": checkpoint.task_id,
            "forked_at_iteration": checkpoint.current_iteration,
        }


# 全局单例
_session_service: Optional[SessionService] = None


def get_session_service() -> SessionService:
    global _session_service
    if _session_service is None:
        from task_persistence import TaskPersistenceManager
        _session_service = SessionService(TaskPersistenceManager())
    return _session_service
