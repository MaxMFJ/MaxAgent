"""
ExecutionLoopMixin — Main autonomous execution loop (run_autonomous).
Extracted from autonomous_agent.py.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, AsyncGenerator

from .action_schema import AgentAction, ActionType, ActionResult, TaskContext
from .exec_phases import PhaseTracker, auto_verify, build_verify_message
from .stop_policy import AdaptiveStopPolicy, StopReason, create_stop_policy
from .thinking_manager import ESCALATION_FORCE_SWITCH, ESCALATION_SKILL_FALLBACK
from .verification_layer import EvidenceCollector, GoalCompletionValidator

# 任务持久化
try:
    from task_persistence import get_persistence_manager, PersistentTaskStatus
except ImportError:
    get_persistence_manager = None
    PersistentTaskStatus = None

try:
    from core.task_state_machine import TaskStateMachine, TaskState
    from core.error_model import to_agent_error, AgentError, ErrorCategory
except ImportError:
    TaskStateMachine = None  # type: ignore
    TaskState = None  # type: ignore
    to_agent_error = None
    AgentError = None
    ErrorCategory = None

logger = logging.getLogger(__name__)


class ExecutionLoopMixin:
    """Mixin providing the main autonomous execution loop for AutonomousAgent."""

    # ------------------------------------------------------------------
    # Quick Q&A detection — 轻量级判断是否绕过 Planner-Reflect 循环
    # ------------------------------------------------------------------
    def _is_quick_qa(self, task: str) -> bool:
        """Detect simple conversational messages that don't need full autonomous loop.
        Uses keyword-based heuristics (no LLM call) to keep it fast.
        """
        # Duck workers always use full autonomous
        if self.isolated_context:
            return False
        try:
            from .model_selector import TaskType
            analysis = self.model_selector.analyzer.analyze(task)
            # Knowledge queries with low complexity → Q&A
            if analysis.task_type == TaskType.KNOWLEDGE_QUERY and analysis.complexity_score <= 4:
                return True
            # Simple operations with very low complexity → Q&A
            if analysis.task_type == TaskType.SIMPLE_OPERATION and analysis.complexity_score <= 3 and analysis.estimated_steps <= 2:
                return True
        except Exception:
            pass
        # Very short messages that look conversational
        if len(task.strip()) < 80 and not any(kw in task.lower() for kw in [
            "创建", "写入", "生成", "下载", "运行", "打开", "设计", "部署", "搜索",
            "create", "write", "generate", "download", "run", "open", "deploy", "search",
            "delegate", "dag", "build", "install",
        ]):
            return True
        return False

    async def _run_quick_qa(
        self, task: str, session_id: str, extra_system_prompt: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fast path for simple Q&A — delegates to AgentCore.run_stream() (function calling).
        Skips planning, reflection, middleware, adaptive stop. ~1 round-trip.
        """
        from app_state import get_agent_core, get_chat_runner
        runner = get_chat_runner() or get_agent_core()
        if not runner:
            yield {"type": "error", "message": "Agent core not available for quick Q&A"}
            return
        logger.info(f"Quick Q&A mode for: {task[:60]}...")
        async for chunk in runner.run_stream(task, session_id=session_id, extra_system_prompt=extra_system_prompt):
            yield chunk

    async def run_autonomous(
        self,
        task: str,
        session_id: str = "default",
        extra_system_prompt: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Unified execution entry point — handles both quick Q&A and complex tasks.
        Quick Q&A: delegates to AgentCore function-calling loop (fast, yields content chunks).
        Complex tasks: full Plan-Execute-Reflect autonomous loop.
        Yields progress updates as the task executes.
        """
        # Quick Q&A fast path — bypass Planner-Reflect for simple questions
        if self._is_quick_qa(task):
            async for chunk in self._run_quick_qa(task, session_id, extra_system_prompt):
                yield chunk
            return

        # Store extra_system_prompt for injection into _generate_action
        self._extra_system_prompt = extra_system_prompt

        task_id = str(uuid.uuid4())[:8]
        # v3.4: store for file handlers (snapshot_manager, etc.)
        self._current_task_id = task_id
        self._current_session_id = session_id
        if self.enable_adaptive_stop:
            self._stop_policy = create_stop_policy(
                task=task,
                max_iterations=self.max_iterations,
                max_tokens=self.max_tokens,
                max_time_seconds=self.max_time_seconds,
                enable_adaptive=True
            )
            initial_max = self._stop_policy.current_max_iterations
        else:
            self._stop_policy = None
            initial_max = self.max_iterations

        context = TaskContext(
            task_id=task_id,
            task_description=task,
            max_iterations=self.max_iterations,
            adaptive_max_iterations=initial_max
        )

        # 桥接会话上下文中的 created_files 到任务的 key_artifacts
        try:
            if self.context_manager:
                conv_ctx = self.context_manager.get_or_create(session_id)
                if conv_ctx.created_files:
                    for file_path in conv_ctx.created_files:
                        context._add_artifact("session_file", file_path, 0)
                    logger.debug(f"Bridged {len(conv_ctx.created_files)} created_files from session to task")
        except Exception as e:
            logger.debug(f"Failed to bridge created_files: {e}")

        # 创建任务持久化检查点
        if get_persistence_manager is not None:
            try:
                persistence = get_persistence_manager()
                await persistence.create_task_checkpoint(
                    task_id=task_id,
                    session_id=session_id,
                    task_description=task,
                    max_iterations=self.max_iterations,
                )
                logger.debug(f"Task checkpoint created: {task_id}")
            except Exception as e:
                logger.warning(f"Failed to create task checkpoint: {e}")

        logger.info(f"Starting autonomous task: {task_id} - {task[:50]}...")

        # Layer 1: Collect user environment context
        user_context = ""
        try:
            user_context = await self._collect_user_context()
            if user_context:
                logger.info(f"User context collected ({len(user_context)} chars)")
        except Exception as e:
            logger.warning(f"User context collection failed: {e}")

        # v3.4: Phase tracker (Gather → Act → Verify)
        self._phase_tracker = PhaseTracker()

        # Per-task escalation state (layer 2 & 3)
        self._escalation_level: int = 0  # ESCALATION_NORMAL
        self._escalation_prompt: str = ""
        self._user_context: str = user_context
        self._skill_guidance_cache = None
        self._mid_reflection_hint: str = ""  # v3.1 中途反思结果，注入下一轮 prompt
        self._current_plan: List[str] = []  # v3.1 Plan-and-Execute 子任务列表
        self._current_plan_index: int = 0

        # v3.5: 重置新架构模块状态
        self._observation_loop.reset()
        self._error_tracker.reset()
        self._confidence_model.reset()
        self._execution_controller.reset()
        self._evidence_collector = EvidenceCollector()
        self._goal_validator = GoalCompletionValidator(self._evidence_collector)
        self._runtime_intel.reset()
        self._goal_tracker = GoalProgressTracker(task)
        # 异步并行 Duck 委派：跟踪已提交但未完成的 Duck 任务
        self._pending_duck_futures: Dict[str, asyncio.Future] = {}  # task_id -> future
        self._pending_duck_descriptions: Dict[str, str] = {}  # task_id -> description
        # 异步 DAG 编排：跟踪已提交但未完成的 DAG 执行
        self._pending_dag_futures: Dict[str, asyncio.Future] = {}  # dag_id -> future
        self._pending_dag_descriptions: Dict[str, str] = {}  # dag_id -> description

        # v3.8: 初始化中间件链
        from .middleware import MiddlewareChain
        from .middlewares import (
            ContextSummarizationMiddleware,
            ActionDeduplicationMiddleware,
            PlanTrackingMiddleware,
            DuckDelegationMiddleware,
        )
        self._middleware_chain = MiddlewareChain()
        self._middleware_chain.add(ContextSummarizationMiddleware(
            token_budget=getattr(self, 'max_tokens', 80000) or 80000,
        ))
        self._mw_dedup = ActionDeduplicationMiddleware()
        self._middleware_chain.add(self._mw_dedup)
        self._mw_plan = PlanTrackingMiddleware()
        self._middleware_chain.add(self._mw_plan)
        self._mw_duck = DuckDelegationMiddleware()
        self._middleware_chain.add(self._mw_duck)

        # 任务启动时注入：匹配的 skill/capsule + 工具提示（截图用 call_tool/screencapture）
        self._task_guidance: str = ""
        try:
            self._task_guidance = await self._build_task_guidance(task)
        except Exception as e:
            logger.debug(f"Task guidance build failed: {e}")

        # Model selection
        self._task_start_time = time.time()
        if self.enable_model_selection:
            try:
                self._current_selection = await self._select_model_for_task(task)
                yield {
                    "type": "model_selected",
                    "model_type": self._current_selection.model_type.value,
                    "tier": self._current_selection.tier.value,
                    "reason": self._current_selection.reason,
                    "task_type": self._current_selection.task_analysis.task_type.value,
                    "complexity": self._current_selection.task_analysis.complexity_score,
                    "model_name": getattr(self.llm, "config", None) and self.llm.config.model or None,
                }
            except Exception as e:
                logger.warning(f"Model selection failed, using default: {e}")
                self._current_selection = None

        # Report task complexity if adaptive stop is enabled
        if self._stop_policy and self._stop_policy.task_complexity:
            yield {
                "type": "task_analysis",
                "task_id": task_id,
                "complexity": self._stop_policy.task_complexity.value,
                "initial_max_iterations": initial_max,
                "adaptive_ceiling": self._stop_policy._adaptive_ceiling
            }

        yield {
            "type": "task_start",
            "task_id": task_id,
            "task": task,
            "max_iterations": initial_max
        }

        # v3: 显式任务状态机
        state_machine = None
        if TaskStateMachine is not None and TaskState is not None:
            state_machine = TaskStateMachine(task_id)
            state_machine.transition(TaskState.RUNNING)
            yield {"type": "task_state", "task_id": task_id, "state": state_machine.state.value}

        # v3.1 Plan-and-Execute: 可选先生成子任务列表
        try:
            from app_state import ENABLE_PLAN_AND_EXECUTE
            if ENABLE_PLAN_AND_EXECUTE:
                plan = await self._generate_plan(task)
                if plan:
                    self._current_plan = plan
                    self._current_plan_index = 0
                    self._goal_tracker.set_sub_goals(plan)
                    self._mw_plan.set_plan(plan)  # v3.8: 同步到中间件
                    yield {"type": "plan_created", "task_id": task_id, "sub_tasks": plan}
        except Exception as e:
            logger.debug("Plan-and-Execute init failed: %s", e)

        try:
            # 硬性上限：防止无限循环（是 max_iterations 的 2 倍）
            HARD_ITERATION_LIMIT = self.max_iterations * 2

            while True:
                context.current_iteration += 1

                # ─── v3.8: 中间件链 before_iteration ───
                async for mw_event in self._middleware_chain.before_iteration(context, context.current_iteration):
                    yield mw_event

                # ─── 收集已完成的并行 Duck 任务结果（兼容旧路径）───
                if self._pending_duck_futures:
                    async for duck_event in self._collect_duck_results(context):
                        yield duck_event

                # ─── 收集已完成的 DAG 多Agent协作结果 ───
                if self._pending_dag_futures:
                    async for dag_event in self._collect_dag_results(context):
                        yield dag_event

                # 硬性上限检查 - 即使所有其他停止条件失效也必须停止
                if context.current_iteration > HARD_ITERATION_LIMIT:
                    logger.error(f"Hard iteration limit reached: {context.current_iteration} > {HARD_ITERATION_LIMIT}")
                    context.status = "force_stopped"
                    context.stop_reason = "hard_limit"
                    context.stop_message = f"Task exceeded hard limit ({HARD_ITERATION_LIMIT} iterations), forcefully terminated"
                    yield {
                        "type": "task_stopped",
                        "task_id": context.task_id,
                        "reason": "hard_limit",
                        "message": context.stop_message,
                        "iterations": context.current_iteration - 1,
                    }
                    break

                # Update adaptive max in context
                if self._stop_policy:
                    context.adaptive_max_iterations = self._stop_policy.current_max_iterations

                logger.info(f"Iteration {context.current_iteration}/{context.adaptive_max_iterations}")

                # 在线模型网关常对同一 token 限制并发，必须等上一轮返回后再发下一请求。非首轮前等待。
                if context.current_iteration > 1 and self.llm is self.remote_llm:
                    await self._call_builder.pre_request_delay(context.current_iteration)

                # v3.6: 检测连续相同 action 循环 — 委托给 ThinkingManager
                if not self._mid_reflection_hint and len(context.action_logs) >= 3:
                    last_log = context.action_logs[-1]
                    _at_val = last_log.action.action_type.value if hasattr(last_log.action.action_type, 'value') else str(last_log.action.action_type)
                    if self._thinking_manager.detect_loop(_at_val, last_log.action.params or {}, context.action_logs):
                        self._mid_reflection_hint = (
                            f"⚠️ You have executed the same action ({_at_val}) 3 times consecutively. "
                            f"This is an ineffective loop. Immediately switch to a different strategy or proceed to the next step."
                        )

                llm_events: List[Dict[str, Any]] = []

                # v3.8.2: 先 yield llm_request_start，让 Duck worker 知道我们正在等 LLM
                yield {
                    "type": "llm_request_start",
                    "iteration": context.current_iteration,
                    "provider": self.llm.config.provider if hasattr(self.llm, 'config') else "",
                    "model": (self.llm.config.model or "") if hasattr(self.llm, 'config') else "",
                    "_pre_call": True,
                }

                action = await self._generate_action(context, llm_events=llm_events)
                for evt in llm_events:
                    yield evt

                if action is None:
                    # 若已有多次成功步骤且产出文件存在，直接视为完成，避免 token 超限后无意义重试
                    steps = len(context.action_logs)
                    success_count = sum(1 for log in context.action_logs if log.result.success)
                    if steps >= 5 and success_count >= 3:
                        from services.duck_task_scheduler import DuckTaskScheduler
                        combined_output = " ".join(
                            str(log.result.output or "") for log in context.action_logs if log.result.output
                        )
                        existing_files = DuckTaskScheduler._extract_file_paths_from_output(combined_output)
                        if existing_files:
                            logger.info(
                                f"Parse failed but output files exist: {existing_files}, treating as success"
                            )
                            action = AgentAction(
                                action_type=ActionType.FINISH,
                                params={
                                    "summary": f"Task completed. Output files: {', '.join(existing_files[:3])}",
                                    "success": True,
                                },
                                reasoning="Output files already exist, treating as completed.",
                            )
                    if action is None:
                        # 检测 LLM 超时（区别于解析失败），注入上下文缩减提示
                        was_llm_timeout = getattr(context, "_last_llm_timeout", False)
                        if was_llm_timeout:
                            context._last_llm_timeout = False
                            context._truncation_hint = (
                                "【LLM 超时警告】上次 LLM 调用超时，可能因为上下文过大或预期输出过长。\n"
                                "请采取以下策略之一：\n"
                                "1. 使用 create_and_run_script 编写 Python 脚本来生成/修改文件，避免在 JSON 中输出大量内容\n"
                                "2. 分步操作：先修改 CSS 部分，再修改 HTML 结构，每步只处理文件的一部分\n"
                                "3. 如果需要大量修改，用 run_shell 执行 sed/awk 等命令或 Python 脚本"
                            )
                        # 若为 write_file 截断场景触发的「再试一次」，不增加 retry_count
                        allow_one_more = getattr(context, "_allow_one_more_retry", False)
                        if allow_one_more:
                            context._allow_one_more_retry = False
                        else:
                            context.retry_count += 1
                        # 解析失败不应消耗正常迭代次数，撤销迭代计数
                        context.current_iteration -= 1

                        backoff_seconds = min(2 ** context.retry_count, 30)
                        retry_reason = "LLM timeout, switching strategy" if was_llm_timeout else "Retrying parse"
                        yield {
                            "type": "retry",
                            "message": f"{retry_reason}… ({context.retry_count}/{context.max_retries}, {backoff_seconds}s later)",
                            "retry_count": context.retry_count,
                            "max_retries": context.max_retries,
                            "backoff_seconds": backoff_seconds,
                        }

                        if self._stop_policy:
                            self._stop_policy.record_iteration(
                                iteration=context.current_iteration,
                                action_type="parse_error",
                                action_params={},
                                output=None,
                                success=False,
                                execution_time_ms=0
                            )

                        if context.retry_count >= context.max_retries:
                            context.status = "parse_error"
                            context.stop_reason = "consecutive_parse_failures"
                            context.stop_message = f"LLM returned unparseable content {context.retry_count} times consecutively. Please check model configuration or simplify the task description."
                            yield {
                                "type": "task_stopped",
                                "task_id": context.task_id,
                                "reason": "parse_error",
                                "message": context.stop_message,
                                "recommendation": "Try: 1) Simplify the task description 2) Check API quota 3) Switch model",
                            }
                            break

                        await asyncio.sleep(backoff_seconds)
                        continue

                context.retry_count = 0  # 解析成功，重置解析失败计数

                yield {
                    "type": "action_plan",
                    "action": action.to_dict(),
                    "iteration": context.current_iteration,
                    "max_iterations": context.adaptive_max_iterations
                }

                if action.action_type == ActionType.FINISH:
                    plan = getattr(self, "_current_plan", []) or []
                    plan_index = getattr(self, "_current_plan_index", 0)
                    _finish_blocked = False

                    # v3.8: 中间件链 check_finish（优先级最高）
                    block_reason = self._middleware_chain.check_finish(action, context) if hasattr(self, '_middleware_chain') else None

                    if not block_reason:
                        pending_ducks = getattr(self, '_pending_duck_futures', {})
                        if pending_ducks:
                            pending_descs = [self._pending_duck_descriptions.get(tid, tid[:8]) for tid in pending_ducks]
                            block_reason = f"There are {len(pending_ducks)} Duck sub-tasks still executing: {', '.join(pending_descs)}. Please wait for them to complete before finishing the task."
                    if not block_reason:
                        pending_dags = getattr(self, '_pending_dag_futures', {})
                        if pending_dags:
                            pending_descs = [self._pending_dag_descriptions.get(did, did[:8]) for did in pending_dags]
                            block_reason = f"There are {len(pending_dags)} DAG multi-agent tasks still executing: {', '.join(pending_descs)}. Please wait for them to complete before finishing the task."
                    if not block_reason:
                        block_reason = self._thinking_manager.should_block_finish(
                            plan, plan_index, context.action_logs
                        )
                    if block_reason:
                        _consecutive_finish_blocks = getattr(context, '_consecutive_finish_blocks', 0) + 1
                        context._consecutive_finish_blocks = _consecutive_finish_blocks
                        if _consecutive_finish_blocks >= 3:
                            logger.warning("FINISH blocked %d times consecutively, force-allowing: %s",
                                           _consecutive_finish_blocks, block_reason)
                            context._consecutive_finish_blocks = 0
                        else:
                            logger.info(f"FINISH rejected ({_consecutive_finish_blocks}/3): {block_reason}")
                            remaining_steps = []
                            if plan and plan_index < len(plan) - 1:
                                remaining_steps = plan[plan_index + 1:]
                            if remaining_steps:
                                next_step_hint = f"Please continue with the next planned step: '{remaining_steps[0]}' ({len(remaining_steps)} steps remaining)"
                            else:
                                next_step_hint = "Please check failed sub-tasks and re-execute, or use another approach to complete the task"
                            feedback_msg = (
                                f"⚠️ FINISH rejected: {block_reason}\n"
                                f"Your task is NOT complete. You cannot output finish. {next_step_hint}.\n"
                                f"Do NOT output finish again. Execute a concrete tool action immediately."
                            )
                            self._mid_reflection_hint = feedback_msg
                            context.add_action_log(action, ActionResult(
                                action_id=action.action_id,
                                success=False,
                                output=feedback_msg,
                                error="finish_blocked",
                            ))
                            _finish_blocked = True
                    else:
                        context._consecutive_finish_blocks = 0

                    if _finish_blocked:
                        yield {
                            "type": "finish_blocked",
                            "reason": block_reason,
                            "consecutive_blocks": _consecutive_finish_blocks,
                            "iteration": context.current_iteration,
                        }
                        continue

                    result = await self._execute_action(action)
                    context.add_action_log(action, result)

                    # v3.5: Goal completion validation via evidence
                    _goal_validation = {}
                    try:
                        _goal_validation = self._goal_validator.check_completion(
                            task_description=context.task_description,
                            action_logs=[
                                {"action_type": log.action.action_type.value, "success": log.result.success}
                                for log in context.action_logs
                            ],
                            claimed_success=action.params.get("success", True),
                        )
                        if _goal_validation.get("warnings"):
                            logger.info(f"Goal validation warnings: {_goal_validation['warnings']}")
                    except Exception as _gv_err:
                        logger.debug("Goal validation error: %s", _gv_err)

                    # 保存检查点 - 任务完成
                    if get_persistence_manager is not None:
                        try:
                            persistence = get_persistence_manager()
                            await persistence.update_action_checkpoint(
                                task_id=task_id,
                                iteration=context.current_iteration,
                                action_type=action.action_type.value,
                                params=action.params,
                                reasoning=action.reasoning,
                                success=result.success,
                                output=result.output,
                                error=result.error,
                            )
                            await persistence.update_task_status(
                                task_id=task_id,
                                status=PersistentTaskStatus.COMPLETED,
                                final_result=action.params.get("summary", "Task completed"),
                            )
                        except Exception as e:
                            logger.warning(f"Failed to save checkpoint on finish: {e}")

                    context.status = "completed"
                    context.stop_reason = "task_complete"
                    context.completed_at = datetime.now()
                    context.final_result = action.params.get("summary", "Task completed")

                    task_success = action.params.get("success", True)
                    execution_time_ms = int((time.time() - self._task_start_time) * 1000) if self._task_start_time else 0

                    if self._current_selection:
                        self.model_selector.record_result(
                            task=task,
                            selection=self._current_selection,
                            success=task_success,
                            execution_time_ms=execution_time_ms
                        )

                    stop_stats = self._stop_policy.get_statistics() if self._stop_policy else {}

                    if state_machine and TaskState is not None:
                        state_machine.transition(TaskState.COMPLETED)
                    action_log = [
                        {"action_type": log.action.action_type.value, "tool_name": log.action.action_type.value}
                        for log in context.action_logs
                    ]
                    total_t = context.total_tokens
                    if total_t == 0 and self._stop_policy and hasattr(self._stop_policy, "cost_tracker"):
                        total_t = self._stop_policy.cost_tracker.total_tokens
                    token_usage = {
                        "prompt_tokens": context.total_prompt_tokens,
                        "completion_tokens": context.total_completion_tokens,
                        "total_tokens": total_t,
                    }
                    yield {
                        "type": "task_complete",
                        "task_id": task_id,
                        "success": task_success,
                        "summary": context.final_result,
                        "total_actions": len(context.action_logs),
                        "iterations": context.current_iteration,
                        "execution_time_ms": execution_time_ms,
                        "action_log": action_log,
                        "token_usage": token_usage,
                        "model_type": self._current_selection.model_type.value if self._current_selection else None,
                        "success_rate": context.get_success_rate(),
                        "stop_policy_stats": stop_stats,
                        "phase_stats": self._phase_tracker.stats() if hasattr(self, "_phase_tracker") else {},
                        "goal_validation": _goal_validation,
                        "goal_progress": self._goal_tracker.get_status_dict(),
                        "tool_metrics": {k: v.for_llm() for k, v in self._runtime_intel.metrics.get_all_metrics().items()},
                    }

                    if self.enable_reflection and self.reflect_llm:
                        try:
                            yield {"type": "reflect_start"}
                            async for reflect_chunk in self._run_reflection(context):
                                yield reflect_chunk
                        except Exception as e:
                            logger.warning(f"Reflection skipped (Ollama may not be running): {e}")
                            yield {"type": "reflect_result", "error": f"Reflection skipped: Ollama not running"}

                    return

                yield {
                    "type": "action_executing",
                    "action_id": action.action_id,
                    "action_type": action.action_type.value
                }

                # v3.5: Pre-observation + Confidence scoring
                _pre_snap = None
                _confidence = 1.0
                try:
                    _pre_snap = await self._observation_loop.pre_observe(
                        iteration=context.current_iteration,
                        action_type=action.action_type.value,
                        params=action.params or {},
                    )
                    _confidence = self._confidence_model.score(
                        action.action_type.value,
                        action.params or {},
                    )
                except Exception as _obs_err:
                    logger.debug("Pre-observation/confidence error: %s", _obs_err)

                # v3.6: Action dedup
                _dedup_skip = False
                try:
                    _dedup_skip = self._check_action_dedup(action, context)
                    if _dedup_skip:
                        logger.info(f"Action dedup: skipping duplicate {action.action_type.value}")
                        result = ActionResult(
                            action_id=action.action_id,
                            success=False,
                            output=None,
                            error="This action is identical to a recently successful step and has been skipped. Please proceed to the next step instead of repeating completed actions.",
                            execution_time_ms=0,
                        )
                        context.add_action_log(action, result)
                        self._mid_reflection_hint = (
                            "⚠️ You just attempted to repeat an already-completed action, which was blocked by the system. "
                            "Please review what has been completed in [Key Artifacts] and execute the remaining steps."
                        )
                        yield {
                            "type": "action_result",
                            "action_id": action.action_id,
                            "success": False,
                            "output": None,
                            "error": "duplicate_action_blocked",
                            "execution_time_ms": 0,
                        }
                        continue
                except Exception as _dedup_err:
                    logger.debug("Action dedup check error: %s", _dedup_err)

                # v3.5: Execution Controller
                _step_record = None
                try:
                    from .error_taxonomy import classify_error
                    _step_record = self._execution_controller.create_step(
                        action.action_type.value
                    )
                    allowed, block_reason = self._execution_controller.can_execute(
                        action.action_type.value, action.params or {}
                    )
                    if not allowed:
                        logger.warning(f"Execution blocked: {block_reason}")
                        _observation_text = f"⚠ {block_reason}"
                        result = ActionResult(
                            action_id=action.action_id,
                            success=False,
                            output=None,
                            error=block_reason,
                            execution_time_ms=0,
                        )
                        context.add_action_log(action, result)
                        yield {
                            "type": "action_result",
                            "action_id": action.action_id,
                            "success": False,
                            "output": None,
                            "error": result.error,
                            "execution_time_ms": 0,
                        }
                        context.consecutive_action_failures += 1
                        continue
                    self._execution_controller.on_step_start(_step_record)
                    _pre_warning = self._runtime_intel.pre_action_check(action.action_type.value)
                    if _pre_warning:
                        logger.info(f"Runtime intel warning: {_pre_warning}")
                except Exception as _ctrl_err:
                    logger.debug("Execution controller error: %s", _ctrl_err)

                if state_machine and TaskState is not None:
                    state_machine.transition(TaskState.WAITING_TOOL)
                result = await self._execute_action(action)
                if state_machine and TaskState is not None:
                    state_machine.transition(TaskState.RUNNING)
                context.add_action_log(action, result)

                # v3.5: Post-observation + Error tracking + Confidence update
                _observation_text = ""
                try:
                    if _pre_snap is not None:
                        _obs = await self._observation_loop.post_observe(
                            iteration=context.current_iteration,
                            action_type=action.action_type.value,
                            params=action.params or {},
                            result=result,
                            pre_snapshot=_pre_snap,
                        )
                        if _obs.has_changes:
                            _observation_text = _obs.for_llm(max_chars=600)
                    self._confidence_model.record_outcome(action.action_type.value, result.success)
                    if not result.success and result.error:
                        from .error_taxonomy import classify_error
                        classified = classify_error(
                            result.error,
                            tool_name=action.action_type.value,
                            action_type=action.action_type.value,
                        )
                        self._error_tracker.record(classified)
                        if self._error_tracker.should_escalate():
                            _observation_text += "\n⚠ Errors keep occurring, consider switching strategy."
                except Exception as _post_err:
                    logger.debug("Post-observation error: %s", _post_err)

                # v3.5: Execution Controller step completion + Runtime Intelligence + Evidence + Goal Tracker
                try:
                    if _step_record is not None:
                        if result.success:
                            self._execution_controller.on_step_success(_step_record)
                        else:
                            _classified_for_ctrl = None
                            if result.error:
                                from .error_taxonomy import classify_error
                                _classified_for_ctrl = classify_error(
                                    result.error,
                                    tool_name=action.action_type.value,
                                    action_type=action.action_type.value,
                                )
                            if _classified_for_ctrl:
                                self._execution_controller.on_step_failure(
                                    _step_record, _classified_for_ctrl
                                )
                    _err_cat_for_metrics = ""
                    if not result.success and result.error:
                        try:
                            from .error_taxonomy import classify_error
                            _cl = classify_error(result.error, tool_name=action.action_type.value, action_type=action.action_type.value)
                            _err_cat_for_metrics = _cl.category.value if _cl else ""
                        except Exception:
                            pass
                    _strategy_advice = self._runtime_intel.record_tool_call(
                        tool_name=action.action_type.value,
                        success=result.success,
                        latency_ms=float(result.execution_time_ms),
                        error_category=_err_cat_for_metrics,
                    )
                    if _strategy_advice and _strategy_advice.advice_type == "avoid":
                        _observation_text += f"\n{_strategy_advice.message}"
                    self._evidence_collector.collect_from_action(
                        action.action_type.value, action.params or {}, result,
                    )
                    self._goal_tracker.record_action(
                        action_type=action.action_type.value,
                        success=result.success,
                        params=action.params,
                        output=str(result.output or "")[:300],
                    )
                except Exception as _intel_err:
                    logger.debug("Post-action intelligence error: %s", _intel_err)

                # v3.4: Phase tracking + automated Verify
                try:
                    verify_note = await auto_verify(action.action_type.value, action.params, result)
                    if _observation_text and not verify_note:
                        verify_note = _observation_text
                    elif _observation_text and verify_note:
                        verify_note = f"{verify_note}\n{_observation_text}"
                    phase_rec = self._phase_tracker.record(
                        iteration=context.current_iteration,
                        action_type=action.action_type.value,
                        success=result.success,
                        verify_note=verify_note,
                    )
                    if verify_note:
                        phase_msg = build_verify_message(verify_note, phase_rec.phase)
                        if phase_msg:
                            # 注入下一轮 _generate_action 的 context
                            context._phase_verify_message = phase_msg
                        yield {
                            "type": "phase_verify",
                            "iteration": context.current_iteration,
                            "phase": phase_rec.phase.value,
                            "note": verify_note,
                            "confidence": _confidence,
                        }
                except Exception as _phase_err:
                    logger.debug("Phase tracking error: %s", _phase_err)

                # 保存检查点 - 每次 action 执行后
                if get_persistence_manager is not None:
                    try:
                        persistence = get_persistence_manager()
                        await persistence.update_action_checkpoint(
                            task_id=task_id,
                            iteration=context.current_iteration,
                            action_type=action.action_type.value,
                            params=action.params,
                            reasoning=action.reasoning,
                            success=result.success,
                            output=result.output,
                            error=result.error,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to save action checkpoint: {e}")

                try:
                    from core.trace_logger import append_span as trace_append_span
                    if trace_append_span:
                        trace_append_span(context.task_id, {
                            "iteration": context.current_iteration,
                            "type": "tool",
                            "action_type": action.action_type.value,
                            "latency_ms": result.execution_time_ms,
                            "success": result.success,
                            "error": result.error[:200] if result.error else None,
                        })
                except ImportError:
                    pass
                if self._stop_policy:
                    token_cost = getattr(self, "_last_llm_tokens", 0)
                    self._stop_policy.record_iteration(
                        iteration=context.current_iteration,
                        action_type=action.action_type.value,
                        action_params=action.params,
                        output=result.output,
                        success=result.success,
                        execution_time_ms=result.execution_time_ms,
                        token_cost=token_cost
                    )

                chunk = {
                    "type": "action_result",
                    "action_id": action.action_id,
                    "success": result.success,
                    "output": str(result.output)[:500] if result.output else None,
                    "error": result.error,
                    "execution_time_ms": result.execution_time_ms
                }
                if isinstance(result.output, dict):
                    if result.output.get("screenshot_path") and result.output.get("image_base64"):
                        yield chunk
                        yield {
                            "type": "screenshot",
                            "screenshot_path": result.output["screenshot_path"],
                            "image_base64": result.output["image_base64"],
                            "mime_type": result.output.get("mime_type", "image/png"),
                        }
                    else:
                        yield chunk
                else:
                    yield chunk

                if not result.success:
                    if action.action_type != ActionType.THINK:
                        context.consecutive_action_failures += 1

                    if action.action_type == ActionType.DELEGATE_DUCK:
                        duck_desc = (action.params.get("description") or "")[:80]
                        duck_type = action.params.get("duck_type", "")
                        self._mid_reflection_hint = (
                            f"⚠️ Sub-task delegation failed ({duck_type}: {duck_desc}). "
                            f"Error: {(result.error or 'unknown')[:100]}. "
                            f"Please retry delegate_duck for this sub-task later. Do NOT finish the task directly."
                        )

                    if context.consecutive_action_failures >= context.max_consecutive_action_failures:
                        logger.warning(
                            f"Consecutive action failures reached {context.consecutive_action_failures}, stopping"
                        )
                        context.status = "consecutive_failures"
                        context.stop_reason = "consecutive_failures"
                        context.stop_message = (
                            f"{context.consecutive_action_failures} consecutive action failures, task incomplete. "
                            f"Last error: {result.error or 'unknown'}"
                        )
                        context.completed_at = datetime.now()

                        if get_persistence_manager is not None:
                            try:
                                persistence = get_persistence_manager()
                                await persistence.update_task_status(
                                    task_id=task_id,
                                    status=PersistentTaskStatus.ERROR,
                                    final_result=context.stop_message,
                                )
                            except Exception as e:
                                logger.debug(f"Failed to update task status: {e}")

                        execution_time_ms = int((time.time() - self._task_start_time) * 1000) if self._task_start_time else 0
                        if self._current_selection:
                            self.model_selector.record_result(
                                task=task,
                                selection=self._current_selection,
                                success=False,
                                execution_time_ms=execution_time_ms
                            )
                        if state_machine and TaskState is not None:
                            state_machine.transition(TaskState.FAILED)
                        yield {
                            "type": "task_stopped",
                            "task_id": task_id,
                            "reason": context.stop_reason,
                            "message": context.stop_message,
                            "recommendation": "Please check the task description or environment (permissions, dependencies, etc.) and retry.",
                            "iterations": context.current_iteration,
                            "execution_time_ms": execution_time_ms,
                            "success_rate": context.get_success_rate(),
                            "stop_policy_stats": self._stop_policy.get_statistics() if self._stop_policy else None
                        }
                        if self.enable_reflection and self.reflect_llm:
                            try:
                                yield {"type": "reflect_start"}
                                async for reflect_chunk in self._run_reflection(context):
                                    yield reflect_chunk
                            except Exception as e:
                                logger.warning(f"Reflection skipped: {e}")
                        return
                else:
                    if action.action_type != ActionType.THINK:
                        context.consecutive_action_failures = 0
                        plan = getattr(self, "_current_plan", [])
                        idx = getattr(self, "_current_plan_index", 0)
                        if plan and idx < len(plan) - 1:
                            self._current_plan_index = idx + 1
                            self._mw_plan.advance()

                # v3.1 中途反思
                try:
                    from app_state import ENABLE_MID_LOOP_REFLECTION, MID_LOOP_REFLECTION_EVERY_N
                except ImportError:
                    ENABLE_MID_LOOP_REFLECTION, MID_LOOP_REFLECTION_EVERY_N = True, 5
                if ENABLE_MID_LOOP_REFLECTION and len(context.action_logs) >= 2:
                    if context.current_iteration % MID_LOOP_REFLECTION_EVERY_N == 0 or context.consecutive_action_failures >= 2:
                        hint = await self._run_mid_loop_reflection(context)
                        if hint:
                            self._mid_reflection_hint = hint

                # Layer 2 & 3: Detect repeated failures and escalate strategy
                new_level = self._detect_repeated_failure(context)
                if new_level > self._escalation_level:
                    self._escalation_level = new_level
                    if new_level >= ESCALATION_FORCE_SWITCH and getattr(self, "_current_plan", None):
                        try:
                            replan = await self._generate_plan(context.task_description)
                            if replan:
                                self._current_plan = replan
                                self._current_plan_index = 0
                                self._goal_tracker.set_sub_goals(replan)
                                self._mw_plan.set_plan(replan)
                                yield {"type": "plan_replanned", "task_id": task_id, "sub_tasks": replan}
                        except Exception as e:
                            logger.debug("Replan failed: %s", e)
                    skill_guidance = ""
                    if new_level >= ESCALATION_SKILL_FALLBACK:
                        if self._skill_guidance_cache is None:
                            self._skill_guidance_cache = self._try_skill_fallback(task)
                        skill_guidance = self._skill_guidance_cache or ""
                    self._escalation_prompt = self._build_escalation_prompt(
                        new_level, context, skill_guidance
                    )
                    logger.info(
                        f"Strategy escalated to level {new_level} "
                        f"(skill_guidance={'yes' if skill_guidance else 'no'})"
                    )
                    yield {
                        "type": "strategy_escalation",
                        "level": new_level,
                        "has_skill_guidance": bool(skill_guidance),
                        "iteration": context.current_iteration,
                    }

                # Check adaptive stop policy
                if self._stop_policy:
                    decision = self._stop_policy.should_continue()

                    if decision.should_stop:
                        context.status = "stopped"
                        context.stop_reason = decision.reason.value if decision.reason else "unknown"
                        context.stop_message = decision.message
                        context.completed_at = datetime.now()

                        if get_persistence_manager is not None:
                            try:
                                persistence = get_persistence_manager()
                                await persistence.update_task_status(
                                    task_id=task_id,
                                    status=PersistentTaskStatus.STOPPED,
                                    final_result=decision.message,
                                )
                            except Exception as e:
                                logger.debug(f"Failed to update task status: {e}")

                        execution_time_ms = int((time.time() - self._task_start_time) * 1000) if self._task_start_time else 0

                        if self._current_selection:
                            self.model_selector.record_result(
                                task=task,
                                selection=self._current_selection,
                                success=False,
                                execution_time_ms=execution_time_ms
                            )
                        if state_machine and TaskState is not None:
                            state_machine.transition(TaskState.FAILED)
                        yield {
                            "type": "task_stopped",
                            "task_id": task_id,
                            "reason": context.stop_reason,
                            "message": decision.message,
                            "recommendation": decision.recommendation,
                            "iterations": context.current_iteration,
                            "execution_time_ms": execution_time_ms,
                            "success_rate": context.get_success_rate(),
                            "stop_policy_stats": self._stop_policy.get_statistics()
                        }

                        if self.enable_reflection and self.reflect_llm:
                            try:
                                yield {"type": "reflect_start"}
                                async for reflect_chunk in self._run_reflection(context):
                                    yield reflect_chunk
                            except Exception as e:
                                logger.warning(f"Reflection skipped: {e}")

                        return

                    if context.current_iteration % 5 == 0:
                        yield {
                            "type": "progress_update",
                            "iteration": context.current_iteration,
                            "max_iterations": self._stop_policy.current_max_iterations,
                            "success_rate": context.get_success_rate(),
                            "summary": self._stop_policy.get_summary()
                        }
                else:
                    if context.current_iteration >= self.max_iterations:
                        context.status = "max_iterations_reached"
                        context.stop_reason = "max_iterations"
                        context.completed_at = datetime.now()
                        if state_machine and TaskState is not None:
                            state_machine.transition(TaskState.FAILED)
                        yield {
                            "type": "error",
                            "error": f"达到最大迭代次数 ({self.max_iterations})"
                        }
                        return

        except Exception as e:
            logger.error(f"Autonomous execution error: {e}", exc_info=True)
            if state_machine and TaskState is not None:
                state_machine.transition(TaskState.FAILED)
            context.status = "error"
            context.stop_reason = "error"
            context.stop_message = str(e)

            if get_persistence_manager is not None:
                try:
                    persistence = get_persistence_manager()
                    await persistence.update_task_status(
                        task_id=task_id,
                        status=PersistentTaskStatus.ERROR,
                        final_result=str(e),
                    )
                except Exception as pe:
                    logger.debug(f"Failed to update task status on error: {pe}")

            if self._stop_policy:
                self._stop_policy.force_stop(StopReason.ERROR, str(e))
            err_payload = {"type": "error", "error": str(e)}
            if AgentError is not None and to_agent_error is not None:
                try:
                    ae = to_agent_error(e, category=ErrorCategory.RUNTIME, retryable=False)
                    err_payload["error_id"] = ae.error_id
                    err_payload["category"] = ae.category.value
                except Exception:
                    pass
            err_payload["stop_policy_stats"] = self._stop_policy.get_statistics() if self._stop_policy else None
            yield err_payload
