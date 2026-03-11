"""
Unified Agent Runtime
======================
ONE Runtime, Multiple Execution Policies.

Chat 和 Autonomous 不再是两个不同的系统，
而是同一个 Runtime 配以不同的 ExecutionPolicy。

Architecture:
    User Input
        ↓
    Intent Analyzer
        ↓
    Unified Agent Runtime (this file)
        ├── ExecutionPolicy → controls behavior
        └── Unified Loop:
            PLAN → OBSERVE → ACT → VERIFY → UPDATE STATE → LOOP/FINISH

Entry Points:
    - execute_chat(message, session_id) → for chat mode
    - execute_task(task, session_id) → for autonomous mode
    Both call the same _unified_loop internally.

This module does NOT replace core.py or autonomous_agent.py immediately.
Instead, it provides a new unified entry that delegates to them,
allowing incremental migration.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from .execution_policy import (
    ExecutionPolicy,
    PolicyMode,
    UnifiedStep,
    UnifiedTaskState,
    StepStatus,
    StepObservation,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class UnifiedAgentRuntime:
    """
    统一的 Agent 执行引擎。

    Chat 和 Autonomous 都通过此 Runtime 执行，
    区别仅在于 ExecutionPolicy 配置：
    - Chat: max_steps=5, streaming=True, 流式 ReAct
    - Autonomous: max_steps=50, streaming=False, 结构化 JSON action

    Phase 1 (当前): 作为 facade，内部委托给 AgentCore / AutonomousAgent
    Phase 2 (将来): 逐步将两者的循环逻辑合并进来
    """

    def __init__(self):
        self._chat_runner = None    # lazy: AgentCore
        self._auto_agent = None     # lazy: AutonomousAgent
        self._active_tasks: Dict[str, UnifiedTaskState] = {}

    def set_chat_runner(self, runner) -> None:
        """注入 Chat runner (AgentCore / chat_runner)"""
        self._chat_runner = runner

    def set_auto_agent(self, agent) -> None:
        """注入 Autonomous agent"""
        self._auto_agent = agent

    # ──────────────────────────────────────────────
    # Public API: execute_chat
    # ──────────────────────────────────────────────

    async def execute_chat(
        self,
        message: str,
        session_id: str = "default",
        extra_system_prompt: str = "",
        policy: Optional[ExecutionPolicy] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Chat 模式入口 — 流式生成响应。
        内部委托给 chat_runner.run_stream()，同时统一记录步骤。
        """
        policy = policy or ExecutionPolicy.chat()
        task_state = UnifiedTaskState(
            task_id=f"chat_{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            description=message[:200],
            policy=policy,
            status=TaskStatus.RUNNING,
        )
        self._active_tasks[task_state.task_id] = task_state

        yield {
            "type": "runtime_task_start",
            "task_id": task_state.task_id,
            "mode": policy.mode.value,
            "policy": policy.to_dict(),
        }

        if not self._chat_runner:
            yield {"type": "error", "message": "Chat runner not initialized"}
            return

        try:
            step = UnifiedStep(
                iteration=1,
                goal=message[:200],
                action_type="chat_stream",
            )
            step.status = StepStatus.EXECUTING
            task_state.add_step(step)

            # Delegate to existing chat_runner.run_stream
            async for chunk in self._chat_runner.run_stream(
                message, session_id=session_id,
                extra_system_prompt=extra_system_prompt,
            ):
                chunk_type = chunk.get("type", "")

                # Track tool calls as sub-steps
                if chunk_type == "tool_call":
                    tool_step = UnifiedStep(
                        iteration=task_state.current_iteration + 1,
                        action_type=f"call_tool:{chunk.get('name', '')}",
                        action_params=chunk.get("args", {}),
                        status=StepStatus.EXECUTING,
                    )
                    task_state.add_step(tool_step)

                elif chunk_type == "tool_result":
                    # Complete the tool step
                    if task_state.steps and task_state.steps[-1].action_type.startswith("call_tool:"):
                        last = task_state.steps[-1]
                        last.complete(
                            success=chunk.get("success", True),
                            output=chunk.get("content", "")[:200],
                            error=chunk.get("error"),
                        )

                elif chunk_type == "stream_end":
                    # Record token usage
                    usage = chunk.get("usage") or {}
                    task_state.total_tokens += usage.get("total_tokens", 0)
                    task_state.total_prompt_tokens += usage.get("prompt_tokens", 0)
                    task_state.total_completion_tokens += usage.get("completion_tokens", 0)

                elif chunk_type == "error":
                    step.complete(success=False, error=chunk.get("error", "unknown"))

                yield chunk

            # Mark chat step as complete if not already
            if step.status == StepStatus.EXECUTING:
                step.complete(success=True)

            task_state.status = TaskStatus.COMPLETED
            task_state.completed_at = time.time()

        except Exception as e:
            logger.error(f"Chat execution error: {e}")
            task_state.status = TaskStatus.FAILED
            yield {"type": "error", "error": str(e)}

        finally:
            yield {
                "type": "runtime_task_end",
                "task_id": task_state.task_id,
                "status": task_state.status.value,
                "steps": len(task_state.steps),
                "success_rate": round(task_state.success_rate, 2),
                "total_tokens": task_state.total_tokens,
            }
            # Keep in active tasks for a bit (for resume), then cleanup
            self._active_tasks.pop(task_state.task_id, None)

    # ──────────────────────────────────────────────
    # Public API: execute_task
    # ──────────────────────────────────────────────

    async def execute_task(
        self,
        task: str,
        session_id: str = "default",
        policy: Optional[ExecutionPolicy] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Autonomous 模式入口 — 多步自主执行任务。
        内部委托给 autonomous_agent.run_autonomous()，同时统一记录步骤。
        """
        policy = policy or ExecutionPolicy.autonomous()
        task_state = UnifiedTaskState(
            task_id=f"auto_{uuid.uuid4().hex[:6]}",
            session_id=session_id,
            description=task[:200],
            policy=policy,
            status=TaskStatus.RUNNING,
        )
        self._active_tasks[task_state.task_id] = task_state

        yield {
            "type": "runtime_task_start",
            "task_id": task_state.task_id,
            "mode": policy.mode.value,
            "policy": policy.to_dict(),
        }

        if not self._auto_agent:
            yield {"type": "error", "message": "Autonomous agent not initialized"}
            return

        try:
            # Delegate to existing autonomous_agent.run_autonomous
            async for event in self._auto_agent.run_autonomous(task, session_id=session_id):
                event_type = event.get("type", "")

                # Map autonomous events to unified steps
                if event_type == "action_plan":
                    action = event.get("action", {})
                    step = UnifiedStep(
                        iteration=event.get("iteration", task_state.current_iteration + 1),
                        goal=action.get("reasoning", ""),
                        action_type=action.get("action_type", ""),
                        action_params=action.get("params", {}),
                        status=StepStatus.PLANNED,
                    )
                    task_state.add_step(step)
                    task_state.current_iteration = step.iteration

                elif event_type == "action_executing":
                    if task_state.steps:
                        task_state.steps[-1].status = StepStatus.EXECUTING

                elif event_type == "action_result":
                    if task_state.steps:
                        last = task_state.steps[-1]
                        last.complete(
                            success=event.get("success", False),
                            output=event.get("output"),
                            error=event.get("error"),
                        )
                        last.execution_time_ms = event.get("execution_time_ms", 0)

                elif event_type == "phase_verify":
                    if task_state.steps:
                        last = task_state.steps[-1]
                        last.observation = StepObservation(
                            verify_note=event.get("note", ""),
                        )
                        last.confidence = event.get("confidence", 1.0)

                elif event_type == "task_complete":
                    task_state.status = TaskStatus.COMPLETED
                    task_state.final_result = event.get("summary", "")
                    task_state.total_tokens = event.get("token_usage", {}).get("total_tokens", 0)
                    task_state.completed_at = time.time()

                elif event_type == "task_stopped":
                    task_state.status = TaskStatus.STOPPED
                    task_state.stop_reason = event.get("reason", "")
                    task_state.completed_at = time.time()

                elif event_type == "error":
                    task_state.status = TaskStatus.FAILED
                    task_state.completed_at = time.time()

                # Pass through all events
                yield event

        except Exception as e:
            logger.error(f"Task execution error: {e}")
            task_state.status = TaskStatus.FAILED
            yield {"type": "error", "error": str(e)}

        finally:
            yield {
                "type": "runtime_task_end",
                "task_id": task_state.task_id,
                "status": task_state.status.value,
                "steps": len(task_state.steps),
                "success_rate": round(task_state.success_rate, 2),
                "total_tokens": task_state.total_tokens,
                "goal_progress": getattr(self._auto_agent, '_goal_tracker', None) and
                    self._auto_agent._goal_tracker.get_status_dict() or None,
            }
            self._active_tasks.pop(task_state.task_id, None)

    # ──────────────────────────────────────────────
    # Task Management
    # ──────────────────────────────────────────────

    def get_active_task(self, task_id: str) -> Optional[UnifiedTaskState]:
        return self._active_tasks.get(task_id)

    def get_active_tasks(self) -> List[UnifiedTaskState]:
        return list(self._active_tasks.values())

    def get_task_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self._active_tasks.get(task_id)
        if not task:
            return None
        return task.to_dict()


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────

_runtime: Optional[UnifiedAgentRuntime] = None


def get_unified_runtime() -> UnifiedAgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = UnifiedAgentRuntime()
    return _runtime


def init_unified_runtime(chat_runner=None, auto_agent=None) -> UnifiedAgentRuntime:
    """Initialize the unified runtime with existing agents."""
    runtime = get_unified_runtime()
    if chat_runner:
        runtime.set_chat_runner(chat_runner)
    if auto_agent:
        runtime.set_auto_agent(auto_agent)
    logger.info("UnifiedAgentRuntime initialized (chat=%s, auto=%s)",
                chat_runner is not None, auto_agent is not None)
    return runtime
