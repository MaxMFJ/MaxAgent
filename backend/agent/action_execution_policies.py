"""
Action execution policies.
Extracts cross-cutting concerns from action execution flow.
"""

import logging
import time
from typing import Optional

from .action_schema import ActionResult
from .safety import validate_action_safe

logger = logging.getLogger(__name__)


class ActionExecutionPolicies:
    """Policy facade for safety, HITL, idempotency, audit and worker guards."""

    _WORKER_FORBIDDEN = {
        "delegate_duck",
        "delegate_dag",
        "spawn_duck",
        "create_agent",
        "create_duck",
        "plan_new_agents",
    }

    def __init__(self, owner):
        self.owner = owner

    @staticmethod
    def action_type_string(action) -> str:
        if hasattr(action.action_type, "value"):
            return str(action.action_type.value).lower()
        return str(action.action_type).lower()

    def _task_id(self) -> str:
        return getattr(self.owner, "_current_task_id", "")

    def _session_id(self) -> str:
        return getattr(self.owner, "_current_session_id", "")

    def check_safety(self, action, start_time: float) -> Optional[ActionResult]:
        ok, err = validate_action_safe(action)
        if ok:
            return None

        try:
            from services.audit_service import append_audit_event
            append_audit_event(
                "action_blocked",
                task_id=self._task_id(),
                session_id=self._session_id(),
                action_type=action.action_type,
                params_summary=str(action.params)[:200],
                result="blocked",
                risk_level="high",
                details={"reason": err},
            )
        except Exception:
            pass

        return ActionResult(
            action_id=action.action_id,
            success=False,
            error=err or "安全校验未通过",
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    def check_idempotent_cache(self, action) -> Optional[ActionResult]:
        try:
            from services.idempotent_service import get_cached_result

            cached = get_cached_result(action.action_type, action.params or {})
            if cached is None:
                return None

            return ActionResult(
                action_id=action.action_id,
                success=cached.get("success", True),
                output=cached.get("output"),
                error=cached.get("error"),
                execution_time_ms=0,
            )
        except Exception:
            return None

    async def check_hitl(self, action, start_time: float) -> Optional[ActionResult]:
        try:
            from services.hitl_service import (
                HitlDecision,
                get_hitl_manager,
                should_require_confirmation,
            )

            if not should_require_confirmation(action.action_type, action.params or {}):
                return None

            mgr = get_hitl_manager()
            mgr.create_request(
                action_id=action.action_id,
                task_id=self._task_id(),
                session_id=self._session_id(),
                action_type=action.action_type,
                params=action.params or {},
            )

            try:
                from connection_manager import ConnectionManager
            except Exception:
                pass

            decision = await mgr.wait_for_decision(action.action_id)
            if decision == HitlDecision.APPROVED:
                return None

            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=f"HITL: 动作被{decision.value}",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
        except ImportError:
            return None

    def apply_worker_workspace_guard(self, action, action_type_str: str) -> None:
        if action_type_str not in ("write_file", "create_and_run_script"):
            return

        try:
            from app_state import get_duck_context as _get_duck_context

            duck_ctx = _get_duck_context()
            if not duck_ctx or not isinstance(duck_ctx, dict):
                return

            ws_dir = duck_ctx.get("workspace_dir", "") or duck_ctx.get("sandbox_dir", "")
            if not ws_dir or not action.params:
                return

            file_path = action.params.get("file_path") or action.params.get("path") or ""
            if not file_path or file_path.startswith(ws_dir):
                return

            import os

            corrected = os.path.join(ws_dir, os.path.basename(file_path))
            logger.warning("[WorkerDuck] Redirecting write: '%s' -> '%s'", file_path, corrected)
            if "file_path" in action.params:
                action.params["file_path"] = corrected
            elif "path" in action.params:
                action.params["path"] = corrected
        except Exception:
            pass

    def check_worker_role_guard(self, action, action_type_str: str, start_time: float) -> Optional[ActionResult]:
        if action_type_str not in self._WORKER_FORBIDDEN:
            return None

        try:
            from app_state import get_duck_context as _get_duck_context

            is_worker = bool(_get_duck_context())
        except Exception:
            is_worker = False

        if not is_worker:
            return None

        return ActionResult(
            action_id=action.action_id,
            success=False,
            error=(
                f"WORKER_DUCK ROLE VIOLATION: Action '{action_type_str}' is forbidden. "
                "Worker Ducks are EXECUTOR_ONLY. "
                "You are the assigned specialist - complete the task using available tools."
            ),
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    def audit_execution(self, action, action_result: ActionResult) -> None:
        try:
            from services.audit_service import append_audit_event

            append_audit_event(
                "action_execute",
                task_id=self._task_id(),
                session_id=self._session_id(),
                action_type=action.action_type,
                params_summary=str(action.params)[:200],
                result="success" if action_result.success else "failure",
                risk_level="low",
            )
        except Exception:
            pass

    def store_idempotent_cache(self, action, action_result: ActionResult) -> None:
        try:
            from services.idempotent_service import store_cached_result

            store_cached_result(
                action.action_type,
                action.params or {},
                {
                    "success": action_result.success,
                    "output": action_result.output,
                    "error": action_result.error,
                },
            )
        except Exception:
            pass
