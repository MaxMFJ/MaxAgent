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


# ---------------------------------------------------------------------------
# Strategy escalation levels — 使用统一模块的常量
# ---------------------------------------------------------------------------
from .thinking_manager import ESCALATION_NORMAL, ESCALATION_FORCE_SWITCH, ESCALATION_SKILL_FALLBACK

# 首步解析加固阈值 — 使用统一模块
from .error_recovery import FIRST_STEP_PLAIN_TEXT_MIN_LEN


AUTONOMOUS_SYSTEM_PROMPT = """You are a fully autonomous macOS Agent that completes tasks on behalf of the user without intervention. You have access to terminal, file system, screenshot, web search, and other tools. Always respond to the user in Chinese (中文). Output your next action in the format below.

## Output Format
You must always output the next action as JSON:
```json
{
  "reasoning": "Why this action is needed",
  "action_type": "action_type_here",
  "params": { ... }
}
```

## Available Action Types

1. **run_shell** - Execute a terminal command
   ```json
   {"action_type": "run_shell", "params": {"command": "ls -la", "working_directory": "/path"}, "reasoning": "..."}
   ```

2. **create_and_run_script** - Create and execute a script
   ```json
   {"action_type": "create_and_run_script", "params": {"language": "python|bash|javascript", "code": "...", "run": true}, "reasoning": "..."}
   ```

3. **read_file** - Read file contents
   ```json
   {"action_type": "read_file", "params": {"path": "/path/to/file"}, "reasoning": "..."}
   ```

4. **write_file** - Write to a file
   ```json
   {"action_type": "write_file", "params": {"path": "/path/to/file", "content": "..."}, "reasoning": "..."}
   ```

5. **move_file** - Move/rename a file
   ```json
   {"action_type": "move_file", "params": {"source": "/path/from", "destination": "/path/to"}, "reasoning": "..."}
   ```

6. **copy_file** - Copy a file
   ```json
   {"action_type": "copy_file", "params": {"source": "/path/from", "destination": "/path/to"}, "reasoning": "..."}
   ```

7. **delete_file** - Delete a file
   ```json
   {"action_type": "delete_file", "params": {"path": "/path/to/file"}, "reasoning": "..."}
   ```

8. **list_directory** - List directory contents
   ```json
   {"action_type": "list_directory", "params": {"path": "/path/to/dir"}, "reasoning": "..."}
   ```

9. **open_app** - Open an application (NOT for sending email; use call_tool(mail) for email)
   ```json
   {"action_type": "open_app", "params": {"app_name": "Safari"}, "reasoning": "..."}
   ```

10. **get_system_info** - Get system information
    ```json
    {"action_type": "get_system_info", "params": {"info_type": "cpu|memory|disk|all"}, "reasoning": "..."}
    ```

11. **call_tool** - Invoke a registered built-in tool (recommended for screenshots, web search, capsules, email, etc.)
   - **Web search** (financials, news, real-time data, weather): {"action_type": "call_tool", "params": {"tool_name": "web_search", "args": {"action": "search|news|get_stock|get_weather", "query": "search terms", "language": "zh-CN"}}, "reasoning": "..."}. You have the web_search tool for real-time info. Use it for research, latest data, weather forecasts — never refuse by saying "I cannot get real-time data". For weather, use action="get_weather" with city name as query.
   - **Send email** (MUST use this; NEVER use open_app to open Mail app): {"action_type": "call_tool", "params": {"tool_name": "mail", "args": {"action": "send", "to": "recipient@example.com", "subject": "Subject", "body": "Body"}}, "reasoning": "..."}. System SMTP is already configured.
   - Full screen screenshot: {"action_type": "call_tool", "params": {"tool_name": "screenshot", "args": {"action": "capture", "area": "full"}}, "reasoning": "..."}
   - **App window screenshot** (e.g. "capture WeChat window"): must pass app_name to capture only that app's window: {"action_type": "call_tool", "params": {"tool_name": "screenshot", "args": {"action": "capture", "app_name": "WeChat"}}, "reasoning": "..."}. Common mappings: WeChat→WeChat, Safari→Safari, Chrome→Google Chrome.
   - Capsule skills: {"action_type": "call_tool", "params": {"tool_name": "capsule", "args": {"action": "find", "task": "keywords"}}, "reasoning": "..."}
   - **Duck status** (when user asks about online Ducks): {"action_type": "call_tool", "params": {"tool_name": "duck_status", "args": {}}, "reasoning": "..."}
   - macOS has no `screenshot` command; use call_tool(tool_name=screenshot) or run_shell with the **screencapture** command.

12. **delegate_duck** - Delegate a sub-task to a Duck agent (when online Ducks are available)
   - Best for: coding, web page creation, crawling, design, and other independently completable sub-tasks; or when parallel execution is needed
   - Check availability first with call_tool(duck_status); if delegation fails (no Duck available), complete the task yourself using write_file / create_and_run_script etc.
   ```json
   {"action_type": "delegate_duck", "params": {"description": "Sub-task description", "duck_type": "coder|designer|crawler|general (optional)", "strategy": "single|multi (optional)"}, "reasoning": "..."}
   ```

13. **think** - Think/analyze (no action taken)
    ```json
    {"action_type": "think", "params": {"thought": "Analyzing the situation..."}, "reasoning": "Need to think about next step"}
    ```

14. **finish** - Complete the task
    ```json
    {"action_type": "finish", "params": {"summary": "Task completion summary", "success": true}, "reasoning": "Task is done"}
    ```

## Execution Phases (think in stages)
- **Gather**: Read files, search, check error messages to understand current state as needed.
- **Act**: Execute one concrete action (run_shell / call_tool / write_file etc.).
- **Verify**: Check tool output to determine if the sub-goal was met, if a retry or strategy change is needed.

## Execution Rules

1. **Output exactly one action per turn**; **never output plain natural language only** — always output JSON format as above (you may add brief reasoning text before the ```json ... ``` block).
2. **If the user is just greeting or making small talk** (e.g. "hello", "good afternoon"), still reply in JSON: output `finish` with `params.summary` containing your greeting and brief description of your capabilities. Never reply with just plain text.
3. **Never output finish before performing the required operations**: if the task requires opening apps, executing commands, screenshots, reading/writing files, etc., you must first output and execute the corresponding action (e.g. open_app, run_shell, call_tool), wait for the result, then output finish based on the outcome. For example, "open WeChat" requires first outputting `open_app` (params.app_name = "WeChat"), then finish after success — never output finish directly claiming "WeChat is open".
4. **Carefully analyze the previous step's result before deciding the next step.**
5. **On error, analyze the cause and attempt to fix it, retrying up to 3 times.**
6. **Output finish when the task is complete.**
7. **Screenshot tasks: once you get a successful screenshot result, output finish immediately — do not take repeated screenshots.**
8. **Prefer batch commands (e.g. mv *.txt dest/) over individual operations.**
9. **Be concise and efficient; avoid unnecessary steps.**
10. **Sending email: MUST use call_tool(tool_name=mail). NEVER use open_app to open the Mail app for sending email (Mail app has many limitations and cannot be reliably automated).**

## GUI Interaction Rules (⚠️ HIGHEST PRIORITY — must strictly follow)

{gui_rules}

## Security Restrictions
- Never execute `rm -rf /` or similar destructive commands
- Never modify critical system files
- All operations are logged

{user_context}

Now, based on the user's task and current context, output the JSON for your next action."""


def _looks_like_json_or_code(text: str) -> bool:
    """委托给 ErrorRecovery 统一判断。"""
    return ErrorRecovery.looks_like_json_or_code(text or "")


class AutonomousAgent:
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
            ActionType.DELEGATE_DUCK: self._handle_delegate_duck,
            ActionType.THINK: self._handle_think,
            ActionType.FINISH: self._handle_finish,
        }
    
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
    # Layer 1: User context enrichment
    # ------------------------------------------------------------------

    async def _collect_user_context(self) -> str:
        """Collect user environment context (locale, timezone, path, approximate location).
        LEGACY PATH (DO NOT EXTEND) — 基础部分与 ContextBuilder.collect_user_context 重叠，
        但此版本含 _get_approximate_location 等增强。待后续统一。
        """
        import asyncio
        import os
        import getpass

        parts: List[str] = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"- Current Time: {now_str}")

        # 实际路径（保存文件、向用户报告时必须用此，禁止用 xxx 或 $(whoami)）
        try:
            username = getpass.getuser()
            desktop = os.path.realpath(os.path.expanduser("~/Desktop"))
            parts.append(f"- Current User: {username}")
            parts.append(f"- Desktop Path: {desktop} (Use this exact path when saving files to Desktop or reporting to the user. NEVER use /Users/xxx/ or $(whoami).)")
        except Exception:
            pass

        # System locale
        try:
            proc = await asyncio.create_subprocess_shell(
                "defaults read NSGlobalDomain AppleLocale 2>/dev/null || echo unknown",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            locale_str = stdout.decode().strip()
            if locale_str and locale_str != "unknown":
                parts.append(f"- System Locale: {locale_str}")
        except Exception:
            pass

        # Timezone
        try:
            tz = time.tzname[0] if time.tzname else "unknown"
            import locale as _locale
            try:
                tz_full = datetime.now().astimezone().tzinfo
                parts.append(f"- Timezone: {tz_full}")
            except Exception:
                parts.append(f"- Timezone: {tz}")
        except Exception:
            pass

        # Approximate location via macOS system or IP geolocation
        city = await self._get_approximate_location()
        if city:
            parts.append(f"- Approximate Location: {city}")

        if not parts:
            return ""

        return "## User Environment\n" + "\n".join(parts)

    async def _get_approximate_location(self) -> str:
        """Best-effort approximate city via system timezone or IP geolocation."""
        import asyncio

        # Strategy 1: derive city from macOS timezone setting
        try:
            proc = await asyncio.create_subprocess_shell(
                "readlink /etc/localtime 2>/dev/null || echo ''",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
            tz_path = stdout.decode().strip()
            # e.g. /var/db/timezone/zoneinfo/Asia/Shanghai -> Shanghai
            if "/" in tz_path:
                city_part = tz_path.rsplit("/", 1)[-1]
                if city_part and city_part not in ("UTC", "GMT", "localtime"):
                    return city_part
        except Exception:
            pass

        # Strategy 2: lightweight IP geolocation (timeout 3s)
        try:
            proc = await asyncio.create_subprocess_shell(
                'curl -s --max-time 3 "http://ip-api.com/json/?fields=city,country" 2>/dev/null',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            data = json.loads(stdout.decode().strip())
            city = data.get("city", "")
            country = data.get("country", "")
            if city:
                return f"{city}, {country}" if country else city
        except Exception:
            pass

        return ""

    # ------------------------------------------------------------------
    # Layer 2: Repeated failure detection & forced strategy switch
    # ------------------------------------------------------------------

    def _detect_repeated_failure(self, context: TaskContext) -> int:
        """
        v3.1: 基于 embedding 相似度或 fallback 到 md5，判断重复失败并返回 escalation 等级。
        阈值从 app_state (ESCALATION_* ) 读取。
        现委托给统一的 ThinkingManager。
        """
        # 同步 app_state 阈值到 ThinkingManager
        try:
            from app_state import (
                ESCALATION_FORCE_AFTER_N,
                ESCALATION_SKILL_AFTER_N,
                ESCALATION_SIMILARITY_THRESHOLD,
            )
            self._thinking_manager._escalation_force_after_n = ESCALATION_FORCE_AFTER_N
            self._thinking_manager._escalation_skill_after_n = ESCALATION_SKILL_AFTER_N
            self._thinking_manager._escalation_similarity_threshold = ESCALATION_SIMILARITY_THRESHOLD
        except ImportError:
            pass
        return self._thinking_manager.detect_repeated_failure(context.action_logs)

    # ------------------------------------------------------------------
    # v3.6  Action dedup — 委托给统一的 ThinkingManager
    # ------------------------------------------------------------------

    def _check_action_dedup(self, action: AgentAction, context: TaskContext) -> bool:
        """委托给统一的 ThinkingManager。"""
        return self._thinking_manager.check_action_dedup(
            action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
            action.params,
            context.action_logs,
        )

    def _build_escalation_prompt(
        self, level: int, context: TaskContext, skill_guidance: str
    ) -> str:
        """Build the escalation injection text for _generate_action."""
        if level == ESCALATION_NORMAL:
            return ""

        recent_types = [
            log.action.action_type.value for log in context.action_logs[-5:]
        ]
        used_methods = ", ".join(dict.fromkeys(recent_types))

        parts: List[str] = []

        if level >= ESCALATION_FORCE_SWITCH:
            parts.append(
                f"⚠️ You have repeatedly tried similar methods but failed to complete the task.\n"
                f"Methods you've used: {used_methods}\n"
                f"You MUST use a completely different approach. Do NOT reuse any of the same commands or tools.\n"
                f"Consider: 1) Use a different tool or API  2) Try a different approach  3) Gather more information first"
            )

        if level >= ESCALATION_SKILL_FALLBACK and skill_guidance:
            parts.append(skill_guidance)

        return "\n\n".join(parts)

    async def _run_mid_loop_reflection(self, context: TaskContext) -> Optional[str]:
        """委托给统一的 ThinkingManager。"""
        try:
            from app_state import ENABLE_MID_LOOP_REFLECTION
            if not ENABLE_MID_LOOP_REFLECTION:
                return None
        except ImportError:
            pass
        recent = context.action_logs[-5:]
        if len(recent) < 2:
            return None
        recent_steps = [
            {
                "action_type": log.action.action_type.value,
                "success": log.result.success,
                "output_snippet": log.result.error or str(log.result.output or ""),
            }
            for log in recent
        ]
        return await self._thinking_manager.run_reflection(
            context.task_description, recent_steps
        )

    async def _generate_plan(self, task: str) -> List[str]:
        """委托给统一的 ThinkingManager。"""
        return await self._thinking_manager.generate_plan(task)

    # ------------------------------------------------------------------
    # Task-start: skill/capsule 扫描与工具提示（避免盲目 run_shell）
    # ------------------------------------------------------------------

    async def _build_task_guidance(self, task: str) -> str:
        """
        任务开始时构建指导：匹配的 skill/capsule + 工具与平台提示（如截图用 call_tool/screencapture）。
        注入到首轮 LLM 上下文，减少盲目 run_shell 错误命令（如 screenshot）。
        """
        parts: List[str] = []
        task_lower = (task or "").lower()

        # 1) 工具与平台提示：截图等常见意图
        if any(k in task for k in ("截图", "截屏", "screenshot", "屏幕")):
            # 指定应用窗口截图（微信窗口、Safari窗口 等）：必须用 app_name，不要用 area:full
            app_window_hint = None
            app_name_map = [
                ("微信", "WeChat"), ("wechat", "WeChat"),
                ("Safari", "Safari"), ("safari", "Safari"),
                ("Chrome", "Google Chrome"), ("chrome", "Google Chrome"),
                ("浏览器", "Safari"), ("钉钉", "DingTalk"), ("飞书", "Lark"),
            ]
            for keyword, app_name in app_name_map:
                if keyword in task and ("窗口" in task or "应用" in task or "程序" in task):
                    app_window_hint = (
                        f"[App Window Screenshot] The user wants to capture the '{keyword}' window. Use app_name parameter to capture only that app's window; do NOT use area:\"full\"."
                        f" Example: call_tool params={{\"tool_name\":\"screenshot\",\"args\":{{\"action\":\"capture\",\"app_name\":\"{app_name}\"}}}}"
                    )
                    break
            if not app_window_hint and ("窗口" in task or "某应用" in task or "指定" in task and "截图" in task):
                app_window_hint = (
                    "[App Window Screenshot] The user wants to capture a specific app's window. Use app_name in args (e.g. app_name:\"WeChat\" for WeChat window); do NOT use area:\"full\" for full screen."
                )
            if app_window_hint:
                parts.append(app_window_hint)
            else:
                parts.append(
                    "[Screenshot] macOS has no 'screenshot' command. For full screen: call_tool params={\"tool_name\":\"screenshot\",\"args\":{\"action\":\"capture\",\"area\":\"full\"}}; "
                    "or run_shell: screencapture -x -t png /tmp/screenshot.png"
                )

        # 1b) 研究/投资/财报类任务：明确可用 web_search 获取实时数据
        if any(k in task for k in ("研究", "财报", "投资", "科技股", "股票", "新闻", "最新", "实时", "调研")):
            parts.append(
                "[Web Research] You have the web_search tool to search web pages, news, financial data, etc. Use call_tool(tool_name=\"web_search\", args={\"action\":\"search\" or \"news\", \"query\":\"keywords\", \"language\":\"zh-CN\"}) to get data. Never refuse by saying you cannot fetch real-time data."
            )

        # 2) 扫描并注入匹配的 skill/capsule（本地注册表优先；N/A 时按需拉取）
        try:
            registry = get_capsule_registry()
            capsules = registry.find_capsule_by_task(task, limit=3, min_score=0.7) if len(registry) > 0 else []

            # 本地未命中，且当前开启了按需拉取 — 异步拉取（不阻塞本轮 LLM 调用）
            if not capsules:
                try:
                    from app_state import ENABLE_ON_DEMAND_SKILL_FETCH
                    if ENABLE_ON_DEMAND_SKILL_FETCH:
                        from .capsule_on_demand import search_and_fetch as _od_fetch
                        capsules = await _od_fetch(task, limit=3, min_score=0.5)
                except Exception as ode:
                    logger.debug(f"On-demand skill fetch skipped: {ode}")

            if capsules:
                parts.append("[Matched Skills] The following skills are relevant to the task; use call_tool to execute:")
                for cap in capsules[:3]:
                    # 从 capsule inputs schema 提取参数信息
                    inputs_hint = ""
                    cap_inputs = getattr(cap, 'inputs', None) or {}
                    if isinstance(cap_inputs, dict) and cap_inputs:
                        param_parts = []
                        for key, schema in cap_inputs.items():
                            desc = schema.get("description", "") if isinstance(schema, dict) else ""
                            default = schema.get("default") if isinstance(schema, dict) else None
                            if default is not None:
                                param_parts.append(f'"{ key}": "({desc}, default:{default})"')
                            else:
                                param_parts.append(f'"{key}": "({desc})"')
                        inputs_hint = "{" + ", ".join(param_parts) + "}"
                    else:
                        inputs_hint = '{"task": "..."}'
                    parts.append(
                        f"  - {cap.id}: {cap.description[:60]}… → "
                        f"call_tool(tool_name=\"capsule\", args={{\"action\":\"execute\", \"capsule_id\":\"{cap.id}\", \"inputs\":{inputs_hint}}})"
                    )
        except Exception as e:
            logger.debug(f"Capsule scan for task guidance: {e}")

        # v3.8: 注入匹配的技能包知识
        try:
            from .skill_pack import get_skill_pack_manager
            skill_injection = get_skill_pack_manager().get_prompt_injection(
                task, max_knowledge_chars=1500
            )
            if skill_injection:
                parts.append(skill_injection)
        except Exception as e:
            logger.debug(f"Skill pack injection failed: {e}")

        if not parts:
            return ""
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Layer 3: Skill / Capsule fallback
    # ------------------------------------------------------------------

    def _try_skill_fallback(self, task: str) -> str:
        """
        Search the CapsuleRegistry for skills relevant to the task.
        Returns formatted guidance text, or empty string if nothing found.

        Note: 按需拉取（async）在 _build_task_guidance 中处理；
              此方法为 escalation 层同步兜底，仅查本地注册表。
        """
        try:
            registry = get_capsule_registry()
            if len(registry) == 0:
                return ""

            capsules = registry.find_capsule_by_task(task, limit=3, min_score=1.0)
            if not capsules:
                return ""

            best = capsules[0]
            steps = best.get_steps()

            lines = [
                f"💡 System found a relevant skill to help complete the task:",
                f"Skill: {best.description}",
                f"Source: {best.source or 'local'}",
            ]

            if steps:
                lines.append("Suggested steps:")
                for i, step in enumerate(steps[:8], 1):
                    desc = step.get("description", "")
                    tool = step.get("tool", step.get("name", ""))
                    if desc:
                        lines.append(f"  {i}. {desc}")
                    elif tool:
                        args_str = json.dumps(step.get("args", step.get("parameters", {})), ensure_ascii=False)
                        lines.append(f"  {i}. Use tool {tool}: {args_str[:120]}")

            lines.append("Please refer to the above suggestions and adjust your execution strategy.")
            return "\n".join(lines)

        except Exception as e:
            logger.debug(f"Skill fallback lookup failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Main autonomous execution loop
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

    async def run_autonomous(
        self,
        task: str,
        session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Run autonomous task execution with adaptive stopping
        Yields progress updates as the task executes
        """
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
        self._escalation_level: int = ESCALATION_NORMAL
        self._escalation_prompt: str = ""
        self._user_context: str = user_context
        self._skill_guidance_cache: Optional[str] = None
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
        
        # v3.8: 初始化中间件链
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
                # （此前 llm_request_start 和 llm_request_end 一起在 _generate_action 完成后才 yield，
                #   导致 LLM 思考期间 Duck worker 无 chunk 收到而误判超时）
                yield {
                    "type": "llm_request_start",
                    "iteration": context.current_iteration,
                    "provider": self.llm.config.provider if hasattr(self.llm, 'config') else "",
                    "model": (self.llm.config.model or "") if hasattr(self.llm, 'config') else "",
                    "_pre_call": True,  # 标记：这是预发射信号，真正的将在 llm_events 中
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
                        # 解析重试：用 retry 类型，前端显示「正在重试…」而非「错误」
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
                    # v3.6: 统一 FINISH Guard — 委托给 ThinkingManager
                    plan = getattr(self, "_current_plan", []) or []
                    plan_index = getattr(self, "_current_plan_index", 0)
                    _finish_blocked = False

                    # v3.8: 中间件链 check_finish（优先级最高）
                    block_reason = self._middleware_chain.check_finish(action, context) if hasattr(self, '_middleware_chain') else None

                    # 向后兼容：若中间件未阻止，再检查原有逻辑
                    if not block_reason:
                        # 额外检查：是否有未完成的异步 Duck 任务
                        pending_ducks = getattr(self, '_pending_duck_futures', {})
                        if pending_ducks:
                            pending_descs = [self._pending_duck_descriptions.get(tid, tid[:8]) for tid in pending_ducks]
                            block_reason = f"There are {len(pending_ducks)} Duck sub-tasks still executing: {', '.join(pending_descs)}. Please wait for them to complete before finishing the task."
                        else:
                            block_reason = self._thinking_manager.should_block_finish(
                                plan, plan_index, context.action_logs
                            )
                    if block_reason:
                        # 连续 FINISH 被阻止次数累计，超过 3 次则强制放行
                        _consecutive_finish_blocks = getattr(context, '_consecutive_finish_blocks', 0) + 1
                        context._consecutive_finish_blocks = _consecutive_finish_blocks
                        if _consecutive_finish_blocks >= 3:
                            logger.warning("FINISH blocked %d times consecutively, force-allowing: %s",
                                           _consecutive_finish_blocks, block_reason)
                            context._consecutive_finish_blocks = 0
                        else:
                            logger.info(f"FINISH rejected ({_consecutive_finish_blocks}/3): {block_reason}")
                            # 构建具体的下一步指导，而不只是告诉 LLM "被阻止了"
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
                        # 向监控面板广播 FINISH 被阻止事件
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
                    
                    # Record result for model selection learning
                    if self._current_selection:
                        self.model_selector.record_result(
                            task=task,
                            selection=self._current_selection,
                            success=task_success,
                            execution_time_ms=execution_time_ms
                        )
                    
                    # Get stop policy statistics
                    stop_stats = self._stop_policy.get_statistics() if self._stop_policy else {}
                    
                    if state_machine and TaskState is not None:
                        state_machine.transition(TaskState.COMPLETED)
                    # action_log 供 HIST 展示 tools_used；token_usage 来自 context 或 stop_policy 累积
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

                # v3.6: Action dedup — 检测与最近成功步骤完全相同的动作，直接跳过
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

                # v3.5: Execution Controller — circuit breaker + step lifecycle
                _step_record = None
                try:
                    _step_record = self._execution_controller.create_step(
                        action.action_type.value
                    )
                    allowed, block_reason = self._execution_controller.can_execute(
                        action.action_type.value, action.params or {}
                    )
                    if not allowed:
                        logger.warning(f"Execution blocked: {block_reason}")
                        _observation_text = f"⚠ {block_reason}"
                        # Synthesize a failed result
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
                    # Pre-action warning from runtime intelligence
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
                    # Update execution controller step
                    if _step_record is not None:
                        if result.success:
                            self._execution_controller.on_step_success(_step_record)
                        else:
                            _classified_for_ctrl = None
                            if result.error:
                                _classified_for_ctrl = classify_error(
                                    result.error,
                                    tool_name=action.action_type.value,
                                    action_type=action.action_type.value,
                                )
                            if _classified_for_ctrl:
                                self._execution_controller.on_step_failure(
                                    _step_record, _classified_for_ctrl
                                )
                    # Record tool metrics for adaptive strategy
                    _err_cat_for_metrics = ""
                    if not result.success and result.error:
                        try:
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
                    # Collect evidence from action
                    self._evidence_collector.collect_from_action(
                        action.action_type.value, action.params or {}, result,
                    )
                    # Feed goal tracker
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
                    # Merge observation text into verify note
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
                            messages.append(phase_msg)
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
                
                if trace_append_span:
                    try:
                        trace_append_span(context.task_id, {
                            "iteration": context.current_iteration,
                            "type": "tool",
                            "action_type": action.action_type.value,
                            "latency_ms": result.execution_time_ms,
                            "success": result.success,
                            "error": result.error[:200] if result.error else None,
                        })
                    except Exception:
                        pass
                # Record iteration in stop policy（含本轮 LLM token 消耗）
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
                # 截图等工具返回 dict 时：action_result 仅带 path（保持消息体小），图片单独发 screenshot chunk 避免大 payload 导致 WebSocket 失败
                if isinstance(result.output, dict):
                    if result.output.get("screenshot_path"):
                        chunk["screenshot_path"] = result.output["screenshot_path"]
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
                    # 只有实际执行的动作（非 think）才计入连续失败
                    # think 只是 LLM 的中间思考，不应影响连续失败计数
                    if action.action_type != ActionType.THINK:
                        context.consecutive_action_failures += 1

                    # v3.6: Duck 失败时注入重试指导，防止 agent 直接 FINISH
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
                        
                        # 更新持久化状态
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
                    # 仅在实际工具成功时重置连续动作失败计数，think 成功不重置
                    if action.action_type != ActionType.THINK:
                        context.consecutive_action_failures = 0
                        # v3.1 成功一步后推进当前子目标索引
                        plan = getattr(self, "_current_plan", [])
                        idx = getattr(self, "_current_plan_index", 0)
                        if plan and idx < len(plan) - 1:
                            self._current_plan_index = idx + 1
                            self._mw_plan.advance()  # v3.8: 同步中间件
                
                # v3.1 中途反思：每 N 步或连续失败时触发，结果写入 _mid_reflection_hint 供下一轮注入
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
                    # v3.1 Replan on escalation (FORCE_SWITCH 或以上)
                    if new_level >= ESCALATION_FORCE_SWITCH and getattr(self, "_current_plan", None):
                        try:
                            replan = await self._generate_plan(context.task_description)
                            if replan:
                                self._current_plan = replan
                                self._current_plan_index = 0
                                self._goal_tracker.set_sub_goals(replan)
                                self._mw_plan.set_plan(replan)  # v3.8: 同步中间件
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
                        
                        # 更新持久化状态
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
                        
                        # Record failure for model selection learning
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
                        
                        # Run reflection on stopped task
                        if self.enable_reflection and self.reflect_llm:
                            try:
                                yield {"type": "reflect_start"}
                                async for reflect_chunk in self._run_reflection(context):
                                    yield reflect_chunk
                            except Exception as e:
                                logger.warning(f"Reflection skipped: {e}")
                        
                        return
                    
                    # Report progress periodically
                    if context.current_iteration % 5 == 0:
                        yield {
                            "type": "progress_update",
                            "iteration": context.current_iteration,
                            "max_iterations": self._stop_policy.current_max_iterations,
                            "success_rate": context.get_success_rate(),
                            "summary": self._stop_policy.get_summary()
                        }
                else:
                    # Fallback to simple iteration check
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
            
            # 更新持久化状态
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
    
    async def _generate_action(
        self, context: TaskContext, llm_events: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[AgentAction]:
        """Generate the next action using LLM with context enrichment.
        If llm_events is provided, append llm_request_start/llm_request_end for monitoring.
        """
        # Build system prompt with user context (layer 1)
        # LEGACY PATH (DO NOT EXTEND) — Autonomous 模式的 system prompt 拼装仍为内联；
        # 新提示注入请通过 ContextBuilder 添加。
        user_ctx = getattr(self, "_user_context", "")
        
        # 注入共享 GUI 规则（single source of truth）
        from .shared_rules import GUI_RULES
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.replace(
            "{gui_rules}", GUI_RULES
        ).replace(
            "{user_context}", user_ctx if user_ctx else ""
        )
        # 注入 Duck 分身身份与专项规范（Local Duck 执行时）
        try:
            from app_state import get_duck_context
            from services.duck_protocol import DuckType
            from services.duck_template import get_template
            duck_ctx = get_duck_context()
            if duck_ctx:
                duck_type_str = duck_ctx.get("duck_type", "general")
                try:
                    dt = DuckType(duck_type_str)
                    template = get_template(dt)
                    # 注入 Duck 模板的完整 system_prompt（含 _design_spec.md、analyze_local_image 等专项规范）
                    template_prompt = template.system_prompt.strip()
                except (ValueError, ImportError):
                    template_prompt = ""
                parts = [
                    f"[Duck Identity] You are {duck_ctx.get('name', 'Duck')}, specialized type: {duck_type_str}."
                ]
                if template_prompt:
                    parts.append(f"\n[Specialization Rules]\n{template_prompt}")
                if duck_ctx.get("skills"):
                    parts.append(f"\nYour specialized skills: {', '.join(duck_ctx['skills'])}. Prioritize using these skills to complete the task.")
                parts.append(
                    "\n[CRITICAL: Execution Rules] You are an executor, NOT a planner. You MUST:\n"
                    "1. Use tools directly (run_shell, write_file, call_tool, etc.) to execute the task — never just describe or plan.\n"
                    "2. If the task requires creating files, output write_file or create_and_run_script actions to actually create them.\n"
                    "3. NEVER output just text analysis or strategy descriptions. Every step must be an executable JSON action.\n"
                    "4. Do NOT finish on the first step unless the task is truly complete (files created, commands executed, etc.).\n"
                    "5. For code/HTML/file creation, use create_and_run_script (NEVER put very long content in write_file's content field)."
                )
                duck_block = "\n".join(parts)
                system_prompt = duck_block + "\n\n---\n\n" + system_prompt
        except Exception:
            pass
        # 注入项目上下文（MACAGENT.md），每轮携带项目约定与能力边界
        project_ctx = get_project_context_for_prompt()
        if project_ctx:
            system_prompt = project_ctx + "\n\n---\n\n" + system_prompt

        # v3.1: 结构化上下文（可选）+ Goal 重述
        try:
            from app_state import USE_SUMMARIZED_CONTEXT, GOAL_RESTATE_EVERY_N
        except ImportError:
            USE_SUMMARIZED_CONTEXT = True
            GOAL_RESTATE_EVERY_N = 6
        if USE_SUMMARIZED_CONTEXT and hasattr(context, "summarize_history_for_llm"):
            # 按 token 预算分配：默认 4000 tokens 给任务上下文
            _ctx_tokens = getattr(self.llm.config, "max_tokens", 4096) or 4096
            context_str = context.summarize_history_for_llm(
                max_recent=5, max_chars=5000, max_context_tokens=min(6000, _ctx_tokens * 2)
            )
        else:
            context_str = context.get_context_for_llm()
        if GOAL_RESTATE_EVERY_N and context.current_iteration > 0 and context.current_iteration % GOAL_RESTATE_EVERY_N == 0:
            context_str = f"[Current Goal] Original task: {context.task_description}\n\n" + context_str
        plan = getattr(self, "_current_plan", []) or []
        plan_index = getattr(self, "_current_plan_index", 0)
        if plan and plan_index < len(plan):
            remaining_count = len(plan) - plan_index
            context_str += (
                f"\n\n[Execution Plan] {len(plan)} total steps, currently on step {plan_index + 1}: {plan[plan_index]}"
                f"\nRemaining: {plan[plan_index:]}"
                f"\n⚠️ You MUST complete all steps in order. Do NOT finish the task before the plan is fully completed."
            )

        # v3.5: 注入环境状态 + 最近观察
        try:
            _env_ctx = self._observation_loop.env_state.get_context_for_llm()
            if _env_ctx and _env_ctx != "环境状态未知":
                context_str += f"\n\n[Environment State] {_env_ctx}"
            _obs_ctx = self._observation_loop.get_recent_observations_for_llm(n=2, max_chars=600)
            if _obs_ctx:
                context_str += f"\n\n[Recent Observations]\n{_obs_ctx}"
        except Exception:
            pass

        # v3.5: 注入任务进度 + 工具指标 + 失败记忆 + 策略建议
        try:
            _goal_ctx = self._goal_tracker.get_context_for_llm(max_chars=400)
            if _goal_ctx:
                context_str += f"\n\n{_goal_ctx}"
            _intel_ctx = self._runtime_intel.get_context_for_llm(max_chars=500)
            if _intel_ctx:
                context_str += f"\n\n{_intel_ctx}"
            _fail_mem = self._execution_controller.failure_memory.get_failure_summary(n=5)
            if _fail_mem:
                context_str += f"\n\n[Failure Memory]\n{_fail_mem}"
        except Exception:
            pass

        # v3.6: 动态注入在线 Duck 信息 — 委托给 ContextBuilder
        duck_status = await ContextBuilder.get_duck_status_context()
        if duck_status:
            context_str += f"\n\n{duck_status}"

        # v3.8: 注入持久化经验事实
        try:
            from .persistent_memory import get_factbase
            fact_hint = get_factbase().recall_for_prompt(context.task_description, max_chars=800)
            if fact_hint:
                context_str += f"\n\n{fact_hint}"
        except Exception:
            pass

        # LEGACY PATH (DO NOT EXTEND) — 消息构建内联；新增消息逻辑请通过 ContextBuilder。
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_str}
        ]
        
        if not context.action_logs:
            first_content = ""
            task_guidance = getattr(self, "_task_guidance", "").strip()
            if task_guidance:
                first_content = f"{task_guidance}\n\n"
            # 注入截断提示（若上轮 JSON 因 token 限制被截断）
            truncation_hint = getattr(context, "_truncation_hint", "")
            if truncation_hint:
                first_content += f"{truncation_hint}\n\n"
                context._truncation_hint = ""  # 只用一次
            first_content += "开始执行任务。请分析任务并输出第一步动作的 JSON。"
            if getattr(context, "retry_count", 0) > 0:
                first_content += "\n\n【重要】你必须只输出一个 JSON 动作（例如 run_shell、call_tool、read_file 等），不要输出大段自然语言说明。即使你认为任务难以完成，也请先输出一个尝试性动作的 JSON。"
            messages.append({
                "role": "user",
                "content": first_content
            })
        else:
            last_log = context.action_logs[-1]
            result_summary = ""
            if last_log.result.success:
                out = last_log.result.output
                out_str = (
                    out.get("content", out.get("output", ""))
                    if isinstance(out, dict) else str(out)
                )
                # read_file / file_operations read 结果需完整传递，避免 Agent 反复读取
                is_read = (
                    last_log.action.action_type == ActionType.READ_FILE
                    or (
                        last_log.action.action_type == ActionType.CALL_TOOL
                        and (last_log.action.params.get("args") or {}).get("action") == "read"
                    )
                )
                out_limit = 10000 if is_read else 300
                result_summary = f"上一步执行成功。输出: {out_str[:out_limit]}{'...[已截断]' if len(out_str) > out_limit else ''}"
                # 截图类任务：一旦截图成功，强制要求立即 finish，避免重复截图
                task_desc = getattr(context, "task_description", "") or ""
                if any(k in task_desc for k in ("截图", "截屏", "screenshot", "屏幕")):
                    if last_log.action.action_type == ActionType.CALL_TOOL and (
                        (last_log.action.params.get("tool_name") or "").lower() == "screenshot"
                    ):
                        result_summary += "\n\n【重要】截图已成功，请立即输出 finish 动作结束任务，勿再截图或重复操作。"
            else:
                result_summary = f"上一步执行失败。错误: {last_log.result.error}"
            
            # Inject escalation prompt (layer 2 & 3) when triggered
            escalation = getattr(self, "_escalation_prompt", "")
            if escalation:
                result_summary += f"\n\n{escalation}"
            # v3.1 中途反思建议回写
            mid_hint = getattr(self, "_mid_reflection_hint", "") or ""
            # v3.8: 合并中间件链提示
            mw_hints = self._middleware_chain.collect_hints(context) if hasattr(self, '_middleware_chain') else ""
            if mw_hints:
                mid_hint = f"{mid_hint}\n{mw_hints}".strip() if mid_hint else mw_hints
            if mid_hint:
                result_summary += f"\n\n【中途反思建议】{mid_hint}"
                self._mid_reflection_hint = ""

            # 重复验证检测 — 委托给 ContextBuilder
            _verify_hint = ContextBuilder.build_verification_hint(context.action_logs)
            if _verify_hint:
                result_summary += f"\n\n{_verify_hint}"

            next_prompt = f"{result_summary}\n\n请分析结果并输出下一步动作的 JSON。"
            # 注入截断提示（若上轮 JSON 因 token 限制被截断）
            truncation_hint = getattr(context, "_truncation_hint", "")
            if truncation_hint:
                next_prompt += f"\n\n{truncation_hint}"
                context._truncation_hint = ""  # 只用一次
            # 多步且任务含报告/生成时，提示避免单次 JSON 过长被截断
            task_desc = getattr(context, "task_description", "") or ""
            if len(context.action_logs) >= 5 and any(k in task_desc for k in ("报告", "生成", "Markdown", "保存")):
                next_prompt += "\n\n【注意】若需写入长报告，请先输出 call_tool(file_operations) 或 write_file，content 可分段；或先 finish 简要总结。避免单次 JSON 过长被截断。"
            # 解析失败重试时，若已有较多步骤，提示简化输出
            if getattr(context, "retry_count", 0) > 0:
                next_prompt += "\n\n【重试提示】上轮输出可能被截断。请只输出一个简洁的 JSON 动作，报告内容不要全部内嵌在 content 中；可先 finish 简要总结，或分步 write_file。"

            # ── 多模态注入：若上一步结果含图像（如 analyze_local_image / capture_and_analyze），
            #    将图像 base64 注入到消息中供视觉模型分析，避免 Agent 反复截图
            _last_output = last_log.result.output if last_log.result.success else None
            _image_base64 = None
            _image_mime = "image/png"
            if isinstance(_last_output, dict):
                _image_base64 = _last_output.get("image_base64")
                _image_mime = _last_output.get("mime_type", "image/png")
            if _image_base64:
                # 构建多模态消息
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": next_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{_image_mime};base64,{_image_base64}",
                                "detail": "high",
                            },
                        },
                    ],
                })
            else:
                messages.append({"role": "user", "content": next_prompt})
        
        llm_start = time.time()
        try:
            import asyncio
            model_info = f"{self.llm.config.provider}/{self.llm.config.model}"
            logger.info(f"Generating action with LLM: {model_info}")
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_start",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                })
            # 多步任务后易输出长 JSON（如报告），提高 max_tokens 避免截断
            extra_tokens = self._call_builder.compute_max_tokens(
                step_count=len(context.action_logs)
            )

            # Phase C：Extended Thinking / CoT 支持
            # v3.5: 上下文压缩 — 在发送给 LLM 前压缩消息列表
            try:
                messages = self._context_compressor.compress(
                    messages,
                    current_query=context.task_description,
                    keep_recent=6,
                )
            except Exception as _comp_err:
                logger.debug("Context compression failed: %s", _comp_err)

            # 安全网：确保 messages 含至少一条 user 消息（防压缩器误删）
            messages = ContextBuilder.ensure_user_message_present(
                messages, context.task_description
            )

            chat_extra_body: Optional[Dict[str, Any]] = None
            try:
                from app_state import (  # type: ignore
                    ENABLE_EXTENDED_THINKING,
                    EXTENDED_THINKING_BUDGET_TOKENS,
                )
            except ImportError:
                ENABLE_EXTENDED_THINKING = False
                EXTENDED_THINKING_BUDGET_TOKENS = 8000
            if ENABLE_EXTENDED_THINKING:
                messages, chat_extra_body = self._call_builder.inject_cot(
                    messages,
                    enable_extended_thinking=True,
                    thinking_budget_tokens=EXTENDED_THINKING_BUDGET_TOKENS,
                )

            chat_coro = self.llm.chat(
                messages=messages,
                max_tokens=extra_tokens,
                extra_body=chat_extra_body,
            )
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(chat_coro)
            else:
                response = await asyncio.wait_for(chat_coro, timeout=120.0)
            raw_content = response.get("content", "")
            content = extract_text_from_content(raw_content)
            finish_reason = response.get("finish_reason", "")
            usage = response.get("usage") or {}
            tokens = usage.get("total_tokens", 0)
            context.total_tokens += tokens
            context.total_prompt_tokens += usage.get("prompt_tokens", 0)
            context.total_completion_tokens += usage.get("completion_tokens", 0)
            setattr(self, "_last_llm_tokens", tokens)
            latency_ms = int((time.time() - llm_start) * 1000)
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": latency_ms,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": tokens,
                    },
                    "response_preview": (content[:200] + "…") if len(content) > 200 else content,
                })

            if not content:
                logger.warning("Empty LLM response (finish_reason=%s)", finish_reason)
                return None

            action = AgentAction.from_llm_response(content)
            if action is None:
                # 诊断：记录 finish_reason（length=截断）、首尾片段，便于定位解析失败原因
                tail = content[-500:] if len(content) > 500 else content
                logger.warning(
                    "Failed to parse LLM output | len=%d | finish_reason=%s | step=%d | first 600: %s",
                    len(content), finish_reason, len(context.action_logs), content[:600]
                )
                logger.warning(
                    "Parse fail | last 500 chars: %s",
                    tail
                )
                # 兜底1：疑似截断的 JSON（finish_reason=length）+ 多步成功 → 视为任务完成，避免无限重试
                steps = len(context.action_logs)
                success_count = sum(1 for log in context.action_logs if log.result.success)
                # 部分 API 网关（如 newapi/claude-haiku）不正确上报 finish_reason=length，
                # 补充检测：completion_tokens 达到本次 max_tokens 上限也视为截断
                completion_tokens = usage.get("completion_tokens", 0)
                _effective_max_tokens = extra_tokens or self.llm.config.max_tokens or 4096
                is_truncated = LLMCallBuilder.is_truncated(
                    finish_reason, completion_tokens, _effective_max_tokens
                )
                if is_truncated and finish_reason != "length":
                    logger.info(
                        "Supplementary truncation detection: completion_tokens=%d >= max_tokens=%d",
                        completion_tokens, _effective_max_tokens,
                    )
                # 条件放宽：截断时 ≥5 步且 ≥3 成功即视为完成；或最后一次重试且 ≥8 步 ≥6 成功（任务已基本完成）
                retry_count = getattr(context, "retry_count", 0)
                is_last_retry = retry_count >= context.max_retries - 1
                if (is_truncated and steps >= 5 and success_count >= 3) or (is_last_retry and steps >= 8 and success_count >= 6):
                        logger.info(
                            "Treating as finish (truncated=%s, last_retry=%s, steps=%d, success=%d)",
                            is_truncated, is_last_retry, steps, success_count,
                        )
                        action = AgentAction(
                            action_type=ActionType.FINISH,
                            params={"summary": "任务已执行多步。请检查桌面或目标路径是否已有生成内容。", "success": True},
                            reasoning="基于已成功步骤视为完成。",
                        )
                # 兜底1.5：截断的 JSON action（首步 write_file 等被截断）→ 注入文件拆分提示并重试
                if action is None and is_truncated and '"action_type"' in content:
                    logger.info(
                        "Truncated JSON action detected at step %d, injecting split-file hint",
                        steps,
                    )
                    # 不创建 finish action，让重试机制加入拆分提示
                    context._truncation_hint = (
                        "【输出被截断警告】你上次尝试输出了过大的 JSON，导致被截断。"
                        "请将大文件内容拆分：使用 create_and_run_script 编写 Python 脚本生成文件，"
                        "或使用 run_shell 通过 cat << 'HEREDOC' 写入。禁止在 write_file 中放入超长内容。"
                    )
                # 兜底2：LLM 返回了纯自然语言（如打招呼回复）时，视为 finish，把整段内容作为 summary 返回
                if action is None:
                    text = content.strip()[:4000]
                    if text and not _looks_like_json_or_code(content):
                        # 第一步且长文本：多为模型“说明无法完成”，先重试强提示 JSON；最后一次重试时不再拒绝，避免连续解析失败
                        retry_count = getattr(context, "retry_count", 0)
                        is_last_retry = retry_count >= context.max_retries - 1
                        if not context.action_logs and len(text) > FIRST_STEP_PLAIN_TEXT_MIN_LEN and not is_last_retry:
                            logger.info(
                                "First step: rejecting long plain-text as finish (len=%d), will retry with JSON reminder",
                                len(text),
                            )
                            action = None
                    elif text and _looks_like_json_or_code(content):
                        # 内容含 JSON 标记但解析失败（GLM/部分模型把 JSON 包在 markdown 代码块里，
                        # 或 max_tokens 截断导致 JSON 不完整）→ 注入格式提示后重试，不当作 finish
                        retry_count = getattr(context, "retry_count", 0)
                        is_last_retry = retry_count >= context.max_retries - 1
                        if not is_last_retry:
                            logger.info(
                                "Content looks like JSON/code but failed to parse (len=%d, finish_reason=%s), injecting format reminder",
                                len(text), finish_reason,
                            )
                            context._truncation_hint = (
                                "【JSON 格式错误】你的上一步输出包含了代码块或 JSON，但系统无法正确解析。"
                                "请直接输出一个纯 JSON 对象，不要用 ```json 代码块包裹，不要在 JSON 前后添加任何说明文字。"
                                '{"action_type": "write_file", "params": {"path": "/path/to/file", "content": "..."}, "reasoning": "..."}'
                            )
                            action = None  # 触发重试
                        else:
                            # 最后一次重试：若内容疑似 write_file 被截断（含 path、content、html 等），
                            # 注入 create_and_run_script 提示并允许再试一次，避免「显示成功但 HTML 为空」
                            has_write_file_indicators = (
                                '"write_file"' in content and '"path"' in content
                                and ('"content"' in content or "'content'" in content)
                                and ("<!DOCTYPE" in content or "<html" in content or "html" in content.lower())
                            )
                            if has_write_file_indicators and len(content) > 2000:
                                logger.info(
                                    "Last retry: content looks like truncated write_file (len=%d), "
                                    "injecting create_and_run_script hint for one more attempt",
                                    len(content),
                                )
                                context._truncation_hint = (
                                    "【输出被截断】你上次尝试在 write_file 的 content 中放入超长 HTML，导致 JSON 被截断无法解析。"
                                    "**必须**改用 create_and_run_script：编写 Python 脚本，在脚本中用变量存储 HTML 字符串，"
                                    "然后 with open(path,'w') as f: f.write(html) 写入文件。禁止在 JSON 的 content 中直接放超长内容。"
                                )
                                context._allow_one_more_retry = True  # 允许再试一次
                                action = None
                            else:
                                logger.info("Last retry: treating JSON-like but unparseable content as finish")
                                action = AgentAction(
                                    action_type=ActionType.FINISH,
                                    params={"summary": text, "success": True},
                                    reasoning="LLM 返回了纯文本回复，已作为最终回复。"
                                )
            
            if action:
                validation_error = validate_action(action)
                if validation_error:
                    logger.warning(f"Action validation failed: {validation_error}")
                    return None
            
            if trace_append_span:
                try:
                    span = {
                        "iteration": context.current_iteration,
                        "type": "llm",
                        "model": model_info,
                        "latency_ms": int((time.time() - llm_start) * 1000),
                        "success": action is not None,
                    }
                    if action is None:
                        span["error"] = "parse_failed"
                    trace_append_span(context.task_id, span)
                except Exception:
                    pass
            return action
            
        except asyncio.TimeoutError:
            logger.error("LLM request timed out (TimeoutPolicy.llm_timeout or 120s fallback)")
            # 标记超时，让调用方区分超时 vs 解析失败，采取不同重试策略
            context._last_llm_timeout = True
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": int((time.time() - llm_start) * 1000),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "response_preview": None,
                    "error": "timeout",
                })
            return None
        except Exception as e:
            logger.error(f"Error generating action: {e}")
            if llm_events is not None:
                llm_events.append({
                    "type": "llm_request_end",
                    "provider": self.llm.config.provider,
                    "model": self.llm.config.model or "",
                    "iteration": context.current_iteration,
                    "latency_ms": int((time.time() - llm_start) * 1000),
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "response_preview": None,
                    "error": str(e)[:200],
                })
            return None
    
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
    
    async def _run_reflection(
        self,
        context: TaskContext
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run reflection on completed task using local LLM (Ollama or LM Studio)"""
        import asyncio
        
        # 使用本地 LLM 管理器自动检测可用的服务
        local_llm_manager = get_local_llm_manager()
        client, config = await local_llm_manager.get_client()
        
        if client is None or config.provider == LocalLLMProvider.NONE:
            logger.warning("No local LLM service available for reflection")
            yield {
                "type": "reflect_result",
                "error": "反思跳过: 本地模型服务未运行 (Ollama/LM Studio)"
            }
            return
        
        logger.info(f"Using {config.provider.value} ({config.model}) for reflection")
        
        reflection_prompt = f"""分析以下任务执行过程，提取经验和改进建议：

任务: {context.task_description}

执行日志:
{json.dumps([log.to_dict() for log in context.action_logs[-20:]], ensure_ascii=False, indent=2)}

请分析：
1. 执行是否高效？有哪些可以优化的地方？
2. 是否有失败的步骤？原因是什么？
3. 提取可复用的策略或模式
4. 给出改进建议

以 JSON 格式输出：
{{
  "efficiency_score": 1-10,
  "successes": ["成功点1", "成功点2"],
  "failures": ["失败点1"],
  "strategies": ["策略1", "策略2"],
  "improvements": ["改进建议1", "改进建议2"]
}}"""
        
        try:
            reflect_coro = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3
            )
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(reflect_coro, timeout=60.0)
            else:
                response = await asyncio.wait_for(reflect_coro, timeout=60.0)
            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw)
            
            yield {
                "type": "reflect_result",
                "reflection": content,
                "provider": config.provider.value,
                "model": config.model
            }
            
        except asyncio.TimeoutError:
            logger.warning(f"Reflection timed out ({config.provider.value})")
            yield {
                "type": "reflect_result",
                "error": f"反思超时: {config.provider.value} 响应过慢"
            }
        except Exception as e:
            logger.error(f"Reflection error: {e}")
            yield {
                "type": "reflect_result",
                "error": str(e)
            }
    
    # Action Handlers
    
    async def _handle_run_shell(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle run_shell action"""
        import asyncio
        import os
        
        command = params.get("command", "")
        working_dir = params.get("working_directory", os.path.expanduser("~"))
        timeout = params.get("timeout", 60)
        
        if not command:
            return {"success": False, "error": "Command is empty"}
        
        if self._is_dangerous_command(command):
            return {"success": False, "error": f"Dangerous command blocked: {command}"}
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            return {
                "success": process.returncode == 0,
                "output": stdout_str or stderr_str,
                "error": stderr_str if process.returncode != 0 else None,
                "exit_code": process.returncode
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用已注册工具（screenshot、capsule、terminal 等），优先使用而非 run_shell 猜测命令。"""
        tool_name = params.get("tool_name", "").strip()
        args = params.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if not tool_name:
            return {"success": False, "error": "call_tool 缺少 tool_name"}

        # 拦截 delegate_duck：强制走阻塞 handler，防止 tool registry 的异步路径导致并发
        if tool_name == "delegate_duck":
            return await self._handle_delegate_duck(args)

        try:
            result = await execute_tool(tool_name, args)
            out = result.data
            # 保留原始结构化输出（dict/list），供 action_result 阶段提取 screenshot_path/image_base64。
            # 仅在极端不可序列化对象时回退为字符串，避免 websocket 序列化报错。
            if out is not None and not isinstance(out, (str, int, float, bool, dict, list, type(None))):
                out = str(out)
            return {
                "success": result.success,
                "output": out,
                "error": result.error,
            }
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    async def _handle_delegate_duck(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        异步委派子任务给 Duck 分身 Agent。
        采用 fire-and-forget 模式：提交任务后立即返回，不阻塞主 Agent。
        Duck 结果通过 _collect_duck_results() 在后续迭代中收集。
        """
        from app_state import IS_DUCK_MODE
        if IS_DUCK_MODE:
            return {"success": False, "error": "Duck 模式下不允许再次委派子任务给其他 Duck"}

        description = params.get("description", "").strip()
        if not description:
            return {"success": False, "error": "delegate_duck 缺少 description"}
        duck_type = params.get("duck_type")
        target_duck_id = params.get("duck_id")
        strategy = params.get("strategy", "single")
        timeout = params.get("timeout", 300)
        task_params = params.get("params", {})

        try:
            from services.duck_task_scheduler import get_task_scheduler, ScheduleStrategy
            from services.duck_protocol import DuckType

            scheduler = get_task_scheduler()
            await scheduler.initialize()

            dt = None
            if duck_type:
                try:
                    dt = DuckType(duck_type)
                except ValueError:
                    pass

            # 使用 asyncio.Future 接收结果（异步，不阻塞）
            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()

            async def on_result(task):
                if not future.done():
                    future.set_result(task)

            task = await scheduler.submit(
                description=description,
                task_type=params.get("task_type", "general"),
                params=task_params,
                priority=params.get("priority", 0),
                timeout=timeout,
                strategy=strategy,
                target_duck_id=target_duck_id,
                target_duck_type=dt,
                callback=on_result,
            )

            from services.duck_protocol import TaskStatus
            if task.status == TaskStatus.PENDING:
                return {
                    "success": False,
                    "output": None,
                    "error": "No available duck to handle this task. Task queued as PENDING.",
                    "task_id": task.task_id,
                }

            # 异步并行模式：注册 future 后立即返回，主 Agent 可继续执行其他动作
            self._pending_duck_futures[task.task_id] = future
            self._pending_duck_descriptions[task.task_id] = description[:100]
            logger.info(f"Duck task {task.task_id} dispatched asynchronously (pending: {len(self._pending_duck_futures)})")

            return {
                "success": True,
                "output": f"子任务已异步委派给 Duck（task_id: {task.task_id}）。Duck 正在后台执行，你可以继续执行其他操作。完成后系统会自动通知结果。",
                "task_id": task.task_id,
                "duck_id": task.assigned_duck_id,
                "async_dispatched": True,
            }

        except ImportError:
            return {"success": False, "error": "Duck task scheduler not available"}
        except Exception as e:
            return {"success": False, "error": f"delegate_duck error: {e}"}

    async def _collect_duck_results(self, context: TaskContext) -> AsyncGenerator[Dict[str, Any], None]:
        """
        非阻塞地收集已完成的并行 Duck 任务结果。
        在每次迭代开始时调用，将已完成的 Duck 结果注入主 Agent 上下文。
        """
        if not self._pending_duck_futures:
            return

        from services.duck_protocol import TaskStatus

        completed_ids = []
        for task_id, future in self._pending_duck_futures.items():
            if future.done():
                completed_ids.append(task_id)

        for task_id in completed_ids:
            future = self._pending_duck_futures.pop(task_id)
            desc = self._pending_duck_descriptions.pop(task_id, "")
            try:
                completed_task = future.result()
                success = completed_task.status == TaskStatus.COMPLETED
                output = completed_task.output
                error = completed_task.error
                duck_id = completed_task.assigned_duck_id

                # 将 Duck 结果作为虚拟 action log 注入上下文，让 LLM 知道结果
                from .action_schema import ActionType
                duck_action = AgentAction(
                    action_type=ActionType.DELEGATE_DUCK,
                    params={"description": desc, "task_id": task_id},
                    reasoning=f"异步 Duck 任务完成（{'成功' if success else '失败'}）",
                )
                duck_result = ActionResult(
                    action_id=duck_action.action_id,
                    success=success,
                    output=output,
                    error=error,
                )
                context.add_action_log(duck_action, duck_result)

                status_text = "✅ 成功" if success else "❌ 失败"
                hint = f"【Duck 异步任务完成】{status_text}：{desc}"
                if output:
                    hint += f"\n结果：{str(output)[:300]}"
                if error:
                    hint += f"\n错误：{error[:200]}"
                # 追加到反思提示
                existing_hint = self._mid_reflection_hint or ""
                self._mid_reflection_hint = f"{existing_hint}\n{hint}".strip()

                yield {
                    "type": "duck_result_collected",
                    "task_id": task_id,
                    "duck_id": duck_id,
                    "success": success,
                    "description": desc,
                    "output": str(output)[:500] if output else None,
                    "error": error,
                    "pending_count": len(self._pending_duck_futures),
                }
                logger.info(f"Duck async result collected: task={task_id} success={success} pending={len(self._pending_duck_futures)}")
            except Exception as e:
                logger.warning(f"Failed to collect duck result for {task_id}: {e}")
                self._pending_duck_descriptions.pop(task_id, None)
    
    async def _handle_create_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_and_run_script action"""
        import asyncio
        import os
        import tempfile
        
        language = params.get("language", "python")
        code = params.get("code", "")
        should_run = params.get("run", True)
        working_dir = params.get("working_directory", os.path.expanduser("~/Desktop"))
        
        if not code:
            return {"success": False, "error": "Code is empty"}
        
        ext_map = {"python": ".py", "bash": ".sh", "javascript": ".js", "shell": ".sh"}
        ext = ext_map.get(language.lower(), ".txt")
        
        runner_map = {"python": "python3", "bash": "bash", "javascript": "node", "shell": "bash"}
        runner = runner_map.get(language.lower())
        
        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=ext,
                delete=False,
                dir=working_dir
            ) as f:
                f.write(code)
                script_path = f.name
            
            if not should_run:
                return {
                    "success": True,
                    "output": f"Script saved to: {script_path}"
                }
            
            if not runner:
                return {
                    "success": False,
                    "error": f"Unsupported language: {language}"
                }
            
            process = await asyncio.create_subprocess_exec(
                runner, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120
            )
            
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            return {
                "success": process.returncode == 0,
                "output": stdout_str or stderr_str,
                "error": stderr_str if process.returncode != 0 else None
            }
            
        except asyncio.TimeoutError:
            return {"success": False, "error": "Script execution timed out (120s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            # 确保临时脚本文件被清理（除非用户要求保留）
            if script_path and should_run:
                try:
                    if os.path.exists(script_path):
                        os.unlink(script_path)
                except Exception:
                    pass  # 忽略清理失败，不影响主逻辑
    
    async def _handle_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle read_file action, supports offset/limit for chunked reading"""
        import os

        path = os.path.expanduser(params.get("path", ""))
        encoding = params.get("encoding", "utf-8")
        offset = int(params.get("offset", 0) or 0)
        limit = int(params.get("limit", 0) or 15000)
        if limit <= 0:
            limit = 15000

        if not path:
            return {"success": False, "error": "Path is empty"}

        if not os.path.exists(path):
            return {"success": False, "error": f"File not found: {path}"}

        # 检测二进制文件（PNG/JPG/PDF 等），避免 UnicodeDecodeError
        BINARY_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
                             '.pdf', '.zip', '.tar', '.gz', '.exe', '.bin',
                             '.mp3', '.mp4', '.mov', '.avi', '.ico', '.tiff'}
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            size = os.path.getsize(path)
            return {
                "success": False,
                "error": f"该文件是二进制文件（{ext}），无法用 read_file 读取文本内容。"
                         f"文件大小：{size} 字节。请使用 run_shell + python 或 screenshot 等工具处理此类文件。"
            }

        try:
            file_size = os.path.getsize(path)
            # Duck 模式下大文件主动拦截：返回摘要+首尾片段，避免全量内容涌入 LLM 上下文
            BIG_FILE_THRESHOLD = 20 * 1024  # 20KB
            # 判断是否为 Duck：优先用 isolated_context（Local Duck），再检查环境变量（Remote Duck）
            is_duck = getattr(self, 'isolated_context', False)
            if not is_duck:
                try:
                    from app_state import IS_DUCK_MODE
                    is_duck = IS_DUCK_MODE
                except ImportError:
                    pass
            # Duck + 大文件 + 从头读取（offset==0）：无论 limit 多少都返回摘要
            if is_duck and file_size > BIG_FILE_THRESHOLD and offset == 0:
                with open(path, "r", encoding=encoding, errors="replace") as f:
                    lines = f.readlines()
                total_lines = len(lines)
                # 首 80 行 + 尾 30 行
                head_lines = 80
                tail_lines = 30
                head = "".join(lines[:head_lines])
                tail = "".join(lines[-tail_lines:]) if total_lines > head_lines + tail_lines else ""
                # 智能摘要
                summary_block = ""
                try:
                    from services.file_structure_service import get_file_structure_summary
                    summary = get_file_structure_summary(path)
                    if summary:
                        summary_block = f"\n\n【结构摘要】\n{summary}"
                except Exception:
                    pass
                omitted = total_lines - head_lines - (tail_lines if tail else 0)
                mid_hint = f"\n\n... [省略中间 {omitted} 行] ...\n\n" if tail and omitted > 0 else ""
                output = (
                    f"【大文件智能读取】文件共 {total_lines} 行（{file_size} 字节），已启用摘要模式。"
                    f"{summary_block}"
                    f"\n\n【前 {head_lines} 行】\n{head}"
                    f"{mid_hint}"
                    f"{'【后 ' + str(tail_lines) + ' 行】' + chr(10) + tail if tail else ''}"
                    f"\n\n⚠️ 【禁止全量读取】你已获得文件结构摘要和首尾内容，禁止再次从 offset=0 读取全文。"
                    f"\n✅ 【正确做法】使用 create_and_run_script 编写 Python 脚本来修改此文件。"
                    f"脚本中 open('{path}') 读全文，用字符串替换/正则修改后写回。"
                    f"\n如只需读取某段代码，用 read_file offset=N limit=M 精确读取。"
                )
                return {
                    "success": True,
                    "output": output,
                    "content": output,
                    "total_size": sum(len(l) for l in lines),
                    "truncated": True,
                    "smart_summary": True,
                }

            with open(path, "r", encoding=encoding, errors="replace") as f:
                full_content = f.read()
            total = len(full_content)

            if offset > 0 or limit < total:
                content = full_content[offset : offset + limit]
                truncated = offset + limit < total
                hint = f"共 {total} 字符，已读 {offset}–{offset + len(content)}。若需后续内容可 read_file offset={offset + len(content)} limit={limit}" if truncated else None
                return {
                    "success": True,
                    "output": content + (f"\n\n[分段提示] {hint}" if hint else ""),
                    "content": content,
                    "total_size": total,
                    "truncated": truncated,
                }
            return {"success": True, "output": full_content, "content": full_content}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle write_file action"""
        import os
        
        path = os.path.expanduser(params.get("path", ""))
        content = params.get("content", "")
        append = params.get("append", False)
        encoding = params.get("encoding", "utf-8")
        
        if not path:
            return {"success": False, "error": "Path is empty"}
        
        # v3.4 snapshot before write
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "write", path,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
            )
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            mode = "a" if append else "w"
            with open(path, mode, encoding=encoding) as f:
                f.write(content)
            
            return {"success": True, "output": f"Written to: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_move_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle move_file action"""
        import shutil
        import os
        
        source = os.path.expanduser(params.get("source", ""))
        destination = os.path.expanduser(params.get("destination", ""))
        
        if not source or not destination:
            return {"success": False, "error": "Source or destination is empty"}
        
        if not os.path.exists(source):
            return {"success": False, "error": f"Source not found: {source}"}
        
        # v3.4 snapshot before move
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "move", source,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
                destination=destination,
            )
        except Exception:
            pass
        try:
            shutil.move(source, destination)
            return {"success": True, "output": f"Moved: {source} -> {destination}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_copy_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle copy_file action"""
        import shutil
        import os
        
        source = os.path.expanduser(params.get("source", ""))
        destination = os.path.expanduser(params.get("destination", ""))
        
        if not source or not destination:
            return {"success": False, "error": "Source or destination is empty"}
        
        if not os.path.exists(source):
            return {"success": False, "error": f"Source not found: {source}"}
        
        # v3.4 snapshot before copy
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "copy", source,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
                destination=destination,
            )
        except Exception:
            pass
        try:
            if os.path.isdir(source):
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            return {"success": True, "output": f"Copied: {source} -> {destination}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle delete_file action"""
        import shutil
        import os
        
        path = os.path.expanduser(params.get("path", ""))
        recursive = params.get("recursive", False)
        
        if not path:
            return {"success": False, "error": "Path is empty"}
        
        if not os.path.exists(path):
            return {"success": False, "error": f"Path not found: {path}"}
        
        # 使用 realpath 规范化路径，防止通过符号链接或 .. 绕过检查
        real_path = os.path.realpath(path)
        home_dir = os.path.realpath(os.path.expanduser("~"))
        
        # 危险路径列表（包括绝对根目录和系统路径）
        dangerous_exact = ["/", "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var", home_dir]
        dangerous_prefixes = ["/System/", "/Library/", "/usr/", "/bin/", "/sbin/", "/etc/", "/var/", "/private/"]
        
        if real_path in dangerous_exact:
            return {"success": False, "error": f"Cannot delete protected path: {real_path}"}
        
        # 检查是否在危险前缀下
        for prefix in dangerous_prefixes:
            if real_path.startswith(prefix):
                return {"success": False, "error": f"Cannot delete system path: {real_path}"}
        
        try:
            if os.path.isdir(real_path):
                if recursive:
                    shutil.rmtree(real_path)
                else:
                    os.rmdir(real_path)
            else:
                os.unlink(real_path)
            return {"success": True, "output": f"Deleted: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_list_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list_directory action"""
        import os
        
        path = os.path.expanduser(params.get("path", ""))
        recursive = params.get("recursive", False)
        pattern = params.get("pattern")
        
        if not path:
            return {"success": False, "error": "Path is empty"}
        
        if not os.path.exists(path):
            return {"success": False, "error": f"Path not found: {path}"}
        
        try:
            if recursive:
                items = []
                for root, dirs, files in os.walk(path):
                    for name in files + dirs:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, path)
                        if pattern and pattern not in name:
                            continue
                        items.append(rel_path)
                        if len(items) > 500:
                            break
                    if len(items) > 500:
                        break
            else:
                items = os.listdir(path)
                if pattern:
                    items = [i for i in items if pattern in i]
            
            return {"success": True, "output": "\n".join(items[:100])}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_open_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle open_app action（通过 runtime adapter）"""
        app_name = params.get("app_name", "")
        if not app_name:
            return {"success": False, "error": "App name is empty"}
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持应用控制"}
        ok, err = await self.runtime_adapter.open_app(app_name=app_name)
        return {
            "success": ok,
            "output": f"Opened: {app_name}" if ok else None,
            "error": err if not ok else None
        }
    
    async def _handle_close_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle close_app action（通过 runtime adapter）"""
        app_name = params.get("app_name", "")
        if not app_name:
            return {"success": False, "error": "App name is empty"}
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持应用控制"}
        ok, err = await self.runtime_adapter.close_app(app_name)
        return {"success": ok, "output": f"Closed: {app_name}" if ok else None, "error": err if not ok else None}
    
    async def _handle_system_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_system_info action"""
        import psutil
        
        info_type = params.get("info_type", "all")
        
        try:
            info = {}
            
            if info_type in ("cpu", "all"):
                info["cpu"] = {
                    "percent": psutil.cpu_percent(interval=0.5),
                    "count": psutil.cpu_count()
                }
            
            if info_type in ("memory", "all"):
                mem = psutil.virtual_memory()
                info["memory"] = {
                    "total_gb": round(mem.total / (1024**3), 2),
                    "used_gb": round(mem.used / (1024**3), 2),
                    "percent": mem.percent
                }
            
            if info_type in ("disk", "all"):
                disk = psutil.disk_usage("/")
                info["disk"] = {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "percent": round(disk.percent, 1)
                }
            
            return {
                "success": True,
                "output": json.dumps(info, indent=2)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_clipboard_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle clipboard_read action（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持剪贴板"}
        ok, content, err = await self.runtime_adapter.clipboard_read()
        return {"success": ok, "output": content if ok else None, "error": err if not ok else None}
    
    async def _handle_clipboard_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle clipboard_write action（通过 runtime adapter）"""
        content = params.get("content", "")
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持剪贴板"}
        ok, err = await self.runtime_adapter.clipboard_write(content)
        return {"success": ok, "output": "Content copied to clipboard" if ok else None, "error": err if not ok else None}
    
    async def _handle_think(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle think action - no actual execution"""
        thought = params.get("thought", "")
        return {"success": True, "output": f"Thought: {thought}"}
    
    async def _handle_finish(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle finish action"""
        summary = params.get("summary", "Task completed")
        success = params.get("success", True)
        return {"success": success, "output": summary}
    
    def _is_dangerous_command(self, command: str) -> bool:
        """Check if command is dangerous (delegate to safety module)."""
        ok, _ = validate_action_safe(
            AgentAction(action_type=ActionType.RUN_SHELL, params={"command": command or ""}, reasoning="")
        )
        return not ok
