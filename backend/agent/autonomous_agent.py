"""
Autonomous Agent Core
Implements fully autonomous task execution with structured actions
"""

import asyncio
import json
import os
import uuid
import logging
import time
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from datetime import datetime

from .llm_client import LLMClient, LLMConfig
from .llm_utils import extract_text_from_content
from .action_schema import (
    AgentAction, ActionType, ActionStatus, ActionResult,
    ActionLog, TaskContext, validate_action
)
from .context_manager import context_manager
from .local_llm_manager import get_local_llm_manager, LocalLLMProvider
from .model_selector import get_model_selector, ModelSelector, ModelType, ModelSelection
from .stop_policy import (
    AdaptiveStopPolicy, StopReason, StopDecision,
    create_stop_policy, TaskComplexity
)
from .capsule_registry import get_capsule_registry
from .safety import validate_action_safe
from .prompt_loader import get_project_context_for_prompt
from .exec_phases import PhaseTracker, infer_phase, auto_verify, build_verify_message, ExecutionPhase
from tools.router import execute_tool

# v3.5: 新架构模块
from .observation_loop import ObservationLoop, get_observation_loop
from .action_confidence import ActionConfidenceModel, get_confidence_model
from .context_compressor import ContextCompressor, get_context_compressor
from .environment_state import EnvironmentStateManager
from .error_taxonomy import classify_error, ErrorTracker
from .action_result_schema import ActionOutcome, ActionResult as StructuredActionResult
from .execution_controller import ExecutionController
from .verification_layer import EvidenceCollector, GoalCompletionValidator
from .runtime_intelligence import RuntimeIntelligence
from .goal_tracker import GoalProgressTracker

# v3.7: 统一引擎模块
from .llm_call_builder import LLMCallBuilder
from .context_builder import ContextBuilder
from .error_recovery import ErrorRecovery
from .execution_engine import ExecutionEngine
from .thinking_manager import ThinkingManager as UnifiedThinkingManager

# v3.8: 中间件框架
from .middleware import MiddlewareChain
from .middlewares import (
    ContextSummarizationMiddleware,
    ActionDeduplicationMiddleware,
    PlanTrackingMiddleware,
    DuckDelegationMiddleware,
)

# 任务持久化
try:
    from task_persistence import get_persistence_manager, PersistentTaskStatus
except ImportError:
    get_persistence_manager = None
    PersistentTaskStatus = None

try:
    from core.task_state_machine import TaskStateMachine, TaskState
    from core.error_model import to_agent_error, AgentError, ErrorCategory
    from core.timeout_policy import get_timeout_policy
    from core.trace_logger import append_span as trace_append_span
except ImportError:
    TaskStateMachine = None  # type: ignore
    TaskState = None  # type: ignore
    to_agent_error = None
    AgentError = None
    ErrorCategory = None
    get_timeout_policy = None
    trace_append_span = None  # type: ignore

logger = logging.getLogger(__name__)


# Mixins — 解耦后的能力模块
from .user_context_mixin import UserContextMixin
from .task_guidance_mixin import TaskGuidanceMixin
from .file_handlers_mixin import FileHandlersMixin
from .system_handlers_mixin import SystemHandlersMixin
from .duck_handlers_mixin import DuckHandlersMixin
from .action_generator_mixin import ActionGeneratorMixin
from .execution_loop_mixin import ExecutionLoopMixin
from .reflection_mixin import ReflectionMixin


class AutonomousAgent(
    UserContextMixin,
    TaskGuidanceMixin,
    FileHandlersMixin,
    SystemHandlersMixin,
    DuckHandlersMixin,
    ActionGeneratorMixin,
    ExecutionLoopMixin,
    ReflectionMixin,
):
    """
    Fully autonomous agent that executes tasks without user intervention
    Uses structured JSON actions for execution
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        local_llm_client: Optional[LLMClient] = None,
        reflect_llm: Optional[LLMClient] = None,
        runtime_adapter=None,
        max_iterations: int = 50,
        enable_reflection: bool = True,
        enable_model_selection: bool = True,
        enable_adaptive_stop: bool = True,
        max_tokens: int = 100000,
        max_time_seconds: int = 600,
        isolated_context: bool = False,
    ):
        self.remote_llm = llm_client  # Remote model (DeepSeek/OpenAI)
        self.runtime_adapter = runtime_adapter  # DI: 平台操作通过 adapter
        self.local_llm = local_llm_client  # Local model (Ollama/LM Studio)
        self.llm = llm_client  # Current active LLM
        self.reflect_llm = reflect_llm
        self.max_iterations = max_iterations
        self.enable_reflection = enable_reflection
        self.enable_model_selection = enable_model_selection
        self.enable_adaptive_stop = enable_adaptive_stop
        self.max_tokens = max_tokens
        self.max_time_seconds = max_time_seconds
        # v3.8: 上下文隔离模式 — Duck 子代理不共享主 Agent 的会话上下文
        self.isolated_context = isolated_context
        self.context_manager = None if isolated_context else context_manager
        self.model_selector = get_model_selector()
        
        # Track current model selection for recording results
        self._current_selection: Optional[ModelSelection] = None
        self._task_start_time: Optional[float] = None
        self._prefer_local: bool = False  # User preference for local models
        
        # Adaptive stop policy (created per task)
        self._stop_policy: Optional[AdaptiveStopPolicy] = None
        
        self._action_handlers: Dict[ActionType, callable] = {}
        self._register_default_handlers()
        
        # v3.5: 新架构模块
        self._observation_loop: ObservationLoop = get_observation_loop()
        self._confidence_model: ActionConfidenceModel = get_confidence_model()
        self._context_compressor: ContextCompressor = get_context_compressor()
        self._error_tracker: ErrorTracker = ErrorTracker()
        self._execution_controller: ExecutionController = ExecutionController()
        self._evidence_collector: EvidenceCollector = EvidenceCollector()
        self._goal_validator: GoalCompletionValidator = GoalCompletionValidator(self._evidence_collector)
        self._runtime_intel: RuntimeIntelligence = RuntimeIntelligence()
        self._goal_tracker: GoalProgressTracker = GoalProgressTracker()

        # v3.7: 统一引擎模块
        _is_duck = False
        try:
            from app_state import IS_DUCK_MODE
            _is_duck = IS_DUCK_MODE
        except ImportError:
            pass
        self._thinking_manager = UnifiedThinkingManager(llm_client, is_duck_mode=_is_duck)
        self._call_builder = LLMCallBuilder(llm_client, is_local_model=False)
    
    def _register_default_handlers(self):
        """Register default action handlers"""
        self._action_handlers = {
            ActionType.RUN_SHELL: self._handle_run_shell,
            ActionType.CREATE_AND_RUN_SCRIPT: self._handle_create_script,
            ActionType.READ_FILE: self._handle_read_file,
            ActionType.WRITE_FILE: self._handle_write_file,
            ActionType.MOVE_FILE: self._handle_move_file,
            ActionType.COPY_FILE: self._handle_copy_file,
            ActionType.DELETE_FILE: self._handle_delete_file,
            ActionType.LIST_DIRECTORY: self._handle_list_directory,
            ActionType.OPEN_APP: self._handle_open_app,
            ActionType.CLOSE_APP: self._handle_close_app,
            ActionType.GET_SYSTEM_INFO: self._handle_system_info,
            ActionType.CLIPBOARD_READ: self._handle_clipboard_read,
            ActionType.CLIPBOARD_WRITE: self._handle_clipboard_write,
            ActionType.CALL_TOOL: self._handle_call_tool,
            ActionType.THINK: self._handle_think,
            ActionType.FINISH: self._handle_finish,
        }
        # Duck 模式下不注册委派 handler，彻底阻止递归创建 DAG/委派
        try:
            from app_state import IS_DUCK_MODE
            if not IS_DUCK_MODE:
                self._action_handlers[ActionType.DELEGATE_DUCK] = self._handle_delegate_duck
                self._action_handlers[ActionType.DELEGATE_DAG] = self._handle_delegate_dag
        except ImportError:
            self._action_handlers[ActionType.DELEGATE_DUCK] = self._handle_delegate_duck
            self._action_handlers[ActionType.DELEGATE_DAG] = self._handle_delegate_dag
    
    def update_llm(self, llm_client: LLMClient, is_local: bool = False):
        """Update LLM client"""
        if is_local:
            self.local_llm = llm_client
        else:
            self.remote_llm = llm_client
        # Default to remote if not using model selection
        if not self.enable_model_selection:
            self.llm = llm_client
    
    def set_reflect_llm(self, llm_client: LLMClient):
        """Set the reflection LLM (usually Ollama local)"""
        self.reflect_llm = llm_client
    
    async def _select_model_for_task(self, task: str) -> ModelSelection:
        """
        Intelligently select the best model for a task
        Based on task analysis and learned strategies
        """
        local_llm_manager = get_local_llm_manager()
        _, local_config = await local_llm_manager.get_client(force_refresh=True)

        local_available = local_config.provider != LocalLLMProvider.NONE
        remote_available = self.remote_llm is not None

        selection = self.model_selector.select(
            task=task,
            local_available=local_available,
            remote_available=remote_available,
            prefer_local=self._prefer_local
        )

        if selection.model_type == ModelType.LOCAL and local_available:
            detected_model = local_config.model
            if self.local_llm is None or self.local_llm.config.model != detected_model:
                from .llm_client import LLMConfig
                self.local_llm = LLMClient(LLMConfig(
                    provider=local_config.provider.value,
                    base_url=local_config.base_url,
                    model=detected_model,
                    api_key=local_config.api_key,
                ))
                logger.info(f"Created local LLM client for detected model: {detected_model}")
            self.llm = self.local_llm
            logger.info(f"Selected LOCAL model ({detected_model}) for task: {selection.reason}")
        else:
            self.llm = self.remote_llm
            logger.info(f"Selected REMOTE model for task: {selection.reason}")

        return selection
    
    def _record_task_result(self, success: bool, execution_time_ms: int = 0):
        """Record task result for model selection learning"""
        if self._current_selection:
            self.model_selector.record_result(
                task=self._current_selection.task_analysis.keywords[0] if self._current_selection.task_analysis.keywords else "",
                selection=self._current_selection,
                success=success,
                execution_time_ms=execution_time_ms
            )

    # ------------------------------------------------------------------
    # Main autonomous execution loop (run_autonomous from ExecutionLoopMixin)
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        session_id: str = "default",
        override_llm: Optional[LLMClient] = None,
    ) -> str:
        """
        同步式入口：消费 run_autonomous 流，返回最终 summary 字符串。
        供 Local Duck worker、Duck client 等调用。
        override_llm: 分身独立 LLM，配置后优先使用，使分身更有效运用大模型。
        """
        old_llm = None
        if override_llm is not None:
            old_llm = self.llm
            self.llm = override_llm
        try:
            summary = ""
            async for chunk in self.run_autonomous(task, session_id=session_id):
                if chunk.get("type") == "task_complete":
                    summary = chunk.get("summary", "") or ""
                    break
                if chunk.get("type") == "task_stopped":
                    summary = chunk.get("message", "") or chunk.get("summary", "") or ""
                    break
                if chunk.get("type") == "error":
                    raise RuntimeError(chunk.get("error", "Unknown error"))
            return summary or "Task ended"
        finally:
            if old_llm is not None:
                self.llm = old_llm

    # 注：_is_quick_qa, _run_quick_qa, run_autonomous → ExecutionLoopMixin
    # 注：_generate_action → ActionGeneratorMixin

    async def _execute_action(self, action: AgentAction) -> ActionResult:
        """Execute a single action. v3.1: 统一安全校验在入口执行。v3.3: +幂等+HITL+审计"""
        start_time = time.time()
        ok, err = validate_action_safe(action)
        if not ok:
            # v3.3: 审计 — 安全拦截
            try:
                from services.audit_service import append_audit_event
                append_audit_event(
                    "action_blocked",
                    task_id=getattr(self, "_current_task_id", ""),
                    session_id=getattr(self, "_current_session_id", ""),
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

        # v3.3: 幂等缓存检查
        try:
            from services.idempotent_service import get_cached_result
            cached = get_cached_result(action.action_type, action.params or {})
            if cached is not None:
                return ActionResult(
                    action_id=action.action_id,
                    success=cached.get("success", True),
                    output=cached.get("output"),
                    error=cached.get("error"),
                    execution_time_ms=0,
                )
        except Exception:
            pass

        # v3.3: HITL 人工审批检查
        try:
            from services.hitl_service import should_require_confirmation, get_hitl_manager, HitlDecision
            if should_require_confirmation(action.action_type, action.params or {}):
                mgr = get_hitl_manager()
                req = mgr.create_request(
                    action_id=action.action_id,
                    task_id=getattr(self, "_current_task_id", ""),
                    session_id=getattr(self, "_current_session_id", ""),
                    action_type=action.action_type,
                    params=action.params or {},
                )
                # 广播确认请求到 WebSocket
                try:
                    from connection_manager import ConnectionManager
                    # 此处不阻塞发送，仅尝试通知客户端
                except Exception:
                    pass
                decision = await mgr.wait_for_decision(action.action_id)
                if decision != HitlDecision.APPROVED:
                    return ActionResult(
                        action_id=action.action_id,
                        success=False,
                        error=f"HITL: 动作被{decision.value}",
                        execution_time_ms=int((time.time() - start_time) * 1000),
                    )
        except ImportError:
            pass

        handler = self._action_handlers.get(action.action_type)
        _at_str = action.action_type.value.lower() if hasattr(action.action_type, "value") else str(action.action_type).lower()

        # ── Worker Duck 工作区路径强制 ───────────────────────────────────────
        # Worker Duck 的 write_file 必须写入 workspace，自动重定向非法路径
        try:
            from app_state import get_duck_context as _gdc_ws
            _duck_ctx = _gdc_ws()
            if _duck_ctx and _at_str in ("write_file", "create_and_run_script"):
                _ws_dir = _duck_ctx.get("workspace_dir", "") or _duck_ctx.get("sandbox_dir", "") if isinstance(_duck_ctx, dict) else ""
                if _ws_dir and action.params:
                    _fp = action.params.get("file_path") or action.params.get("path") or ""
                    if _fp and not _fp.startswith(_ws_dir):
                        import os as _os
                        _corrected = _os.path.join(_ws_dir, _os.path.basename(_fp))
                        logger.warning(
                            f"[WorkerDuck] Redirecting write: '{_fp}' → '{_corrected}'"
                        )
                        if "file_path" in action.params:
                            action.params["file_path"] = _corrected
                        elif "path" in action.params:
                            action.params["path"] = _corrected
        except Exception:
            pass

        # ── Worker Duck 角色隔离守卫 ─────────────────────────────────────────
        # Worker Duck 不允许调用委派/编排类动作，这些是 Supervisor 专属权限
        _WORKER_FORBIDDEN = {
            "delegate_duck", "delegate_dag", "spawn_duck",
            "create_agent", "create_duck", "plan_new_agents",
        }
        if _at_str in _WORKER_FORBIDDEN:
            try:
                from app_state import get_duck_context as _gdc
                _is_worker = bool(_gdc())
            except Exception:
                _is_worker = False
            if _is_worker:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=(
                        f"⛔ WORKER_DUCK ROLE VIOLATION: Action '{_at_str}' is forbidden. "
                        f"Worker Ducks are EXECUTOR_ONLY. "
                        f"You are the assigned specialist — complete the task using available tools."
                    ),
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )
        # ─────────────────────────────────────────────────────────────────────

        if not handler:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=f"No handler for action type: {action.action_type}"
            )
        
        try:
            result = await handler(action.params)
            execution_time = int((time.time() - start_time) * 1000)
            
            action_result = ActionResult(
                action_id=action.action_id,
                success=result.get("success", True),
                output=result.get("output"),
                error=result.get("error"),
                execution_time_ms=execution_time
            )

            # v3.3: 审计 — 动作执行
            try:
                from services.audit_service import append_audit_event
                append_audit_event(
                    "action_execute",
                    task_id=getattr(self, "_current_task_id", ""),
                    session_id=getattr(self, "_current_session_id", ""),
                    action_type=action.action_type,
                    params_summary=str(action.params)[:200],
                    result="success" if action_result.success else "failure",
                    risk_level="low",
                )
            except Exception:
                pass

            # v3.3: 幂等缓存存储
            try:
                from services.idempotent_service import store_cached_result
                store_cached_result(
                    action.action_type,
                    action.params or {},
                    {"success": action_result.success, "output": action_result.output, "error": action_result.error},
                )
            except Exception:
                pass

            return action_result
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=str(e),
                execution_time_ms=execution_time
            )
    
