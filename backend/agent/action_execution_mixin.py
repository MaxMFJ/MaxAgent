"""Action execution mixin.

This mixin only orchestrates the execution flow. Cross-cutting concerns are
delegated to ActionExecutionPolicies to avoid method bloat.
"""

import time

from .action_result_schema import ActionOutcome
from .action_schema import ActionResult


class ActionExecutionMixin:
    async def _execute_action(self, action) -> ActionResult:
        """Execute a single action via policy-driven pipeline."""
        start_time = time.time()

        policy_result = self._action_policies.check_safety(action, start_time)
        if policy_result is not None:
            return policy_result

        policy_result = self._action_policies.check_idempotent_cache(action)
        if policy_result is not None:
            return policy_result

        policy_result = await self._action_policies.check_hitl(action, start_time)
        if policy_result is not None:
            return policy_result

        handler = self._action_handlers.get(action.action_type)
        action_type_str = self._action_policies.action_type_string(action)
        self._action_policies.apply_worker_workspace_guard(action, action_type_str)
        policy_result = self._action_policies.check_worker_role_guard(
            action, action_type_str, start_time
        )
        if policy_result is not None:
            return policy_result

        if not handler:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=f"No handler for action type: {action.action_type}"
            )

        try:
            structured_result = await self._action_executor.execute(
                action_type=action_type_str,
                params=action.params or {},
                handler=handler,
                iteration=getattr(getattr(self, "_current_context", None), "current_iteration", 0),
                action_id=action.action_id,
                observe=False,
            )

            action_result = ActionResult(
                action_id=action.action_id,
                success=structured_result.outcome == ActionOutcome.SUCCESS,
                output=structured_result.data,
                error=str(structured_result.error) if structured_result.error else None,
                execution_time_ms=structured_result.duration_ms,
            )

            self._action_policies.audit_execution(action, action_result)
            self._action_policies.store_idempotent_cache(action, action_result)

            return action_result
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
