"""
Autonomous Agent Core
Implements fully autonomous task execution with structured actions
"""

import json
import uuid
import hashlib
import logging
import time
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from datetime import datetime

from .llm_client import LLMClient, LLMConfig
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy escalation levels for the three-layer defense
# ---------------------------------------------------------------------------
ESCALATION_NORMAL = 0          # No intervention
ESCALATION_FORCE_SWITCH = 1    # Force a different approach (layer 2)
ESCALATION_SKILL_FALLBACK = 2  # Inject skill guidance (layer 3)


AUTONOMOUS_SYSTEM_PROMPT = """你是一个完全自主执行的 macOS Agent，名叫 MacAgent。你会自动完成用户的任务，无需用户干预。

## 输出格式
你必须始终以 JSON 格式输出下一步动作：
```json
{
  "reasoning": "解释为什么执行这个动作",
  "action_type": "动作类型",
  "params": { ... }
}
```

## 可用的动作类型

1. **run_shell** - 执行终端命令
   ```json
   {"action_type": "run_shell", "params": {"command": "ls -la", "working_directory": "/path"}, "reasoning": "..."}
   ```

2. **create_and_run_script** - 创建并执行脚本
   ```json
   {"action_type": "create_and_run_script", "params": {"language": "python|bash|javascript", "code": "...", "run": true}, "reasoning": "..."}
   ```

3. **read_file** - 读取文件内容
   ```json
   {"action_type": "read_file", "params": {"path": "/path/to/file"}, "reasoning": "..."}
   ```

4. **write_file** - 写入文件
   ```json
   {"action_type": "write_file", "params": {"path": "/path/to/file", "content": "..."}, "reasoning": "..."}
   ```

5. **move_file** - 移动/重命名文件
   ```json
   {"action_type": "move_file", "params": {"source": "/path/from", "destination": "/path/to"}, "reasoning": "..."}
   ```

6. **copy_file** - 复制文件
   ```json
   {"action_type": "copy_file", "params": {"source": "/path/from", "destination": "/path/to"}, "reasoning": "..."}
   ```

7. **delete_file** - 删除文件
   ```json
   {"action_type": "delete_file", "params": {"path": "/path/to/file"}, "reasoning": "..."}
   ```

8. **list_directory** - 列出目录内容
   ```json
   {"action_type": "list_directory", "params": {"path": "/path/to/dir"}, "reasoning": "..."}
   ```

9. **open_app** - 打开应用程序
   ```json
   {"action_type": "open_app", "params": {"app_name": "Safari"}, "reasoning": "..."}
   ```

10. **get_system_info** - 获取系统信息
    ```json
    {"action_type": "get_system_info", "params": {"info_type": "cpu|memory|disk|all"}, "reasoning": "..."}
    ```

11. **think** - 思考/分析（不执行任何操作）
    ```json
    {"action_type": "think", "params": {"thought": "分析当前情况..."}, "reasoning": "需要思考下一步"}
    ```

12. **finish** - 完成任务
    ```json
    {"action_type": "finish", "params": {"summary": "任务完成总结", "success": true}, "reasoning": "任务已完成"}
    ```

## 执行规则

1. **每次只输出一个动作**
2. **仔细分析上一步的执行结果后再决定下一步**
3. **遇到错误时，分析原因并尝试修复，最多重试 3 次**
4. **任务完成后必须输出 finish 动作**
5. **优先使用批量命令（如 mv *.txt dest/）而不是逐个操作**
6. **保持简洁高效，避免不必要的步骤**

## 安全限制
- 禁止执行 `rm -rf /` 等危险命令
- 禁止修改系统关键文件
- 所有操作都会被记录

{user_context}

现在，根据用户的任务和当前上下文，输出下一步动作的 JSON。"""


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
        max_time_seconds: int = 600
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
        self.context_manager = context_manager
        self.model_selector = get_model_selector()
        
        # Track current model selection for recording results
        self._current_selection: Optional[ModelSelection] = None
        self._task_start_time: Optional[float] = None
        self._prefer_local: bool = False  # User preference for local models
        
        # Adaptive stop policy (created per task)
        self._stop_policy: Optional[AdaptiveStopPolicy] = None
        
        self._action_handlers: Dict[ActionType, callable] = {}
        self._register_default_handlers()
    
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
        """Collect user environment context (locale, timezone, approximate location)."""
        import asyncio
        import os

        parts: List[str] = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts.append(f"- 当前时间: {now_str}")

        # System locale
        try:
            proc = await asyncio.create_subprocess_shell(
                "defaults read NSGlobalDomain AppleLocale 2>/dev/null || echo unknown",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            locale_str = stdout.decode().strip()
            if locale_str and locale_str != "unknown":
                parts.append(f"- 系统语言/区域: {locale_str}")
        except Exception:
            pass

        # Timezone
        try:
            tz = time.tzname[0] if time.tzname else "unknown"
            import locale as _locale
            try:
                tz_full = datetime.now().astimezone().tzinfo
                parts.append(f"- 时区: {tz_full}")
            except Exception:
                parts.append(f"- 时区: {tz}")
        except Exception:
            pass

        # Approximate location via macOS system or IP geolocation
        city = await self._get_approximate_location()
        if city:
            parts.append(f"- 大致位置: {city}")

        if not parts:
            return ""

        return "## 用户环境\n" + "\n".join(parts)

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
        Analyze recent action logs for repetitive failure patterns.
        Returns escalation level: ESCALATION_NORMAL / FORCE_SWITCH / SKILL_FALLBACK.
        """
        logs = context.action_logs
        if len(logs) < 2:
            return ESCALATION_NORMAL

        recent = logs[-5:]

        # Hash each action's (type + truncated output) to detect similarity
        hashes: List[str] = []
        for log in recent:
            sig = f"{log.action.action_type.value}:{str(log.result.output)[:200]}"
            hashes.append(hashlib.md5(sig.encode()).hexdigest()[:10])

        # Count how many of the last N are identical
        last_hash = hashes[-1]
        consecutive_same = 0
        for h in reversed(hashes):
            if h == last_hash:
                consecutive_same += 1
            else:
                break

        if consecutive_same >= 3:
            return ESCALATION_SKILL_FALLBACK
        if consecutive_same >= 2:
            return ESCALATION_FORCE_SWITCH

        return ESCALATION_NORMAL

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
                f"⚠️ 你已经连续多次尝试了相似的方法但都未能成功完成任务。\n"
                f"你之前使用的方法: {used_methods}\n"
                f"你必须使用完全不同的方法。禁止再次使用与之前相同的命令或工具。\n"
                f"考虑: 1) 使用不同的工具或 API  2) 换一种思路  3) 先获取更多信息再行动"
            )

        if level >= ESCALATION_SKILL_FALLBACK and skill_guidance:
            parts.append(skill_guidance)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Layer 3: Skill / Capsule fallback
    # ------------------------------------------------------------------

    def _try_skill_fallback(self, task: str) -> str:
        """
        Search the CapsuleRegistry for skills relevant to the task.
        Returns formatted guidance text, or empty string if nothing found.
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
                f"💡 系统找到了一个相关技能可以帮助你完成任务:",
                f"技能: {best.description}",
                f"来源: {best.source or 'local'}",
            ]

            if steps:
                lines.append("建议步骤:")
                for i, step in enumerate(steps[:8], 1):
                    desc = step.get("description", "")
                    tool = step.get("tool", step.get("name", ""))
                    if desc:
                        lines.append(f"  {i}. {desc}")
                    elif tool:
                        args_str = json.dumps(step.get("args", step.get("parameters", {})), ensure_ascii=False)
                        lines.append(f"  {i}. 使用工具 {tool}: {args_str[:120]}")

            lines.append("请参考以上建议调整你的执行策略。")
            return "\n".join(lines)

        except Exception as e:
            logger.debug(f"Skill fallback lookup failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Main autonomous execution loop
    # ------------------------------------------------------------------

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
        
        # Initialize adaptive stop policy
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
        
        logger.info(f"Starting autonomous task: {task_id} - {task[:50]}...")
        
        # Layer 1: Collect user environment context
        user_context = ""
        try:
            user_context = await self._collect_user_context()
            if user_context:
                logger.info(f"User context collected ({len(user_context)} chars)")
        except Exception as e:
            logger.warning(f"User context collection failed: {e}")

        # Per-task escalation state (layer 2 & 3)
        self._escalation_level: int = ESCALATION_NORMAL
        self._escalation_prompt: str = ""
        self._user_context: str = user_context
        self._skill_guidance_cache: Optional[str] = None
        
        # Model selection
        self._task_start_time = time.time()
        if self.enable_model_selection:
            try:
                self._current_selection = await self._select_model_for_task(task)
                yield {
                    "type": "model_selected",
                    "model_type": self._current_selection.model_type.value,
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
        
        try:
            while True:
                context.current_iteration += 1
                
                # Update adaptive max in context
                if self._stop_policy:
                    context.adaptive_max_iterations = self._stop_policy.current_max_iterations
                
                logger.info(f"Iteration {context.current_iteration}/{context.adaptive_max_iterations}")
                
                action = await self._generate_action(context)
                
                if action is None:
                    yield {
                        "type": "error",
                        "error": "无法解析 LLM 输出的动作"
                    }
                    context.retry_count += 1
                    
                    # Record failed iteration
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
                        context.stop_reason = "consecutive_failures"
                        context.stop_message = "连续解析失败"
                        break
                    continue
                
                context.retry_count = 0
                
                yield {
                    "type": "action_plan",
                    "action": action.to_dict(),
                    "iteration": context.current_iteration,
                    "max_iterations": context.adaptive_max_iterations
                }
                
                if action.action_type == ActionType.FINISH:
                    result = await self._execute_action(action)
                    context.add_action_log(action, result)
                    context.status = "completed"
                    context.stop_reason = "task_complete"
                    context.completed_at = datetime.now()
                    context.final_result = action.params.get("summary", "任务完成")
                    
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
                    
                    yield {
                        "type": "task_complete",
                        "task_id": task_id,
                        "success": task_success,
                        "summary": context.final_result,
                        "total_actions": len(context.action_logs),
                        "iterations": context.current_iteration,
                        "execution_time_ms": execution_time_ms,
                        "model_type": self._current_selection.model_type.value if self._current_selection else None,
                        "success_rate": context.get_success_rate(),
                        "stop_policy_stats": stop_stats
                    }
                    
                    if self.enable_reflection and self.reflect_llm:
                        try:
                            yield {"type": "reflect_start"}
                            async for reflect_chunk in self._run_reflection(context):
                                yield reflect_chunk
                        except Exception as e:
                            logger.warning(f"Reflection skipped (Ollama may not be running): {e}")
                            yield {"type": "reflect_result", "error": f"反思跳过: Ollama 未运行"}
                    
                    return
                
                yield {
                    "type": "action_executing",
                    "action_id": action.action_id,
                    "action_type": action.action_type.value
                }
                
                result = await self._execute_action(action)
                context.add_action_log(action, result)
                
                # Record iteration in stop policy
                if self._stop_policy:
                    self._stop_policy.record_iteration(
                        iteration=context.current_iteration,
                        action_type=action.action_type.value,
                        action_params=action.params,
                        output=result.output,
                        success=result.success,
                        execution_time_ms=result.execution_time_ms
                    )
                
                yield {
                    "type": "action_result",
                    "action_id": action.action_id,
                    "success": result.success,
                    "output": str(result.output)[:500] if result.output else None,
                    "error": result.error,
                    "execution_time_ms": result.execution_time_ms
                }
                
                if not result.success:
                    context.retry_count += 1
                    if context.retry_count >= context.max_retries:
                        logger.warning(f"Max retries reached for action type: {action.action_type}")
                
                # Layer 2 & 3: Detect repeated failures and escalate strategy
                new_level = self._detect_repeated_failure(context)
                if new_level > self._escalation_level:
                    self._escalation_level = new_level
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
                        
                        execution_time_ms = int((time.time() - self._task_start_time) * 1000) if self._task_start_time else 0
                        
                        # Record failure for model selection learning
                        if self._current_selection:
                            self.model_selector.record_result(
                                task=task,
                                selection=self._current_selection,
                                success=False,
                                execution_time_ms=execution_time_ms
                            )
                        
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
                        
                        yield {
                            "type": "error",
                            "error": f"达到最大迭代次数 ({self.max_iterations})"
                        }
                        return
            
        except Exception as e:
            logger.error(f"Autonomous execution error: {e}", exc_info=True)
            context.status = "error"
            context.stop_reason = "error"
            context.stop_message = str(e)
            
            if self._stop_policy:
                self._stop_policy.force_stop(StopReason.ERROR, str(e))
            
            yield {
                "type": "error",
                "error": str(e),
                "stop_policy_stats": self._stop_policy.get_statistics() if self._stop_policy else None
            }
    
    async def _generate_action(self, context: TaskContext) -> Optional[AgentAction]:
        """Generate the next action using LLM with context enrichment."""
        # Build system prompt with user context (layer 1)
        user_ctx = getattr(self, "_user_context", "")
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.replace(
            "{user_context}", user_ctx if user_ctx else ""
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context.get_context_for_llm()}
        ]
        
        if not context.action_logs:
            messages.append({
                "role": "user",
                "content": f"开始执行任务。请分析任务并输出第一步动作的 JSON。"
            })
        else:
            last_log = context.action_logs[-1]
            result_summary = ""
            if last_log.result.success:
                result_summary = f"上一步执行成功。输出: {str(last_log.result.output)[:300]}"
            else:
                result_summary = f"上一步执行失败。错误: {last_log.result.error}"
            
            # Inject escalation prompt (layer 2 & 3) when triggered
            escalation = getattr(self, "_escalation_prompt", "")
            if escalation:
                result_summary += f"\n\n{escalation}"

            messages.append({
                "role": "user",
                "content": f"{result_summary}\n\n请分析结果并输出下一步动作的 JSON。"
            })
        
        try:
            import asyncio
            model_info = f"{self.llm.config.provider}/{self.llm.config.model}"
            logger.info(f"Generating action with LLM: {model_info}")
            # 设置 120 秒超时
            response = await asyncio.wait_for(
                self.llm.chat(messages=messages),
                timeout=120.0
            )
            content = response.get("content", "")

            if not content:
                logger.warning("Empty LLM response")
                return None

            action = AgentAction.from_llm_response(content)
            if action is None:
                logger.warning(
                    "Failed to parse LLM output (len=%d, first 800 chars): %s",
                    len(content), content[:800]
                )
            
            if action:
                validation_error = validate_action(action)
                if validation_error:
                    logger.warning(f"Action validation failed: {validation_error}")
                    return None
            
            return action
            
        except asyncio.TimeoutError:
            logger.error("LLM request timed out after 120 seconds")
            return None
        except Exception as e:
            logger.error(f"Error generating action: {e}")
            return None
    
    async def _execute_action(self, action: AgentAction) -> ActionResult:
        """Execute a single action"""
        start_time = time.time()
        
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
            
            return ActionResult(
                action_id=action.action_id,
                success=result.get("success", True),
                output=result.get("output"),
                error=result.get("error"),
                execution_time_ms=execution_time
            )
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
            # 设置 60 秒超时
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": reflection_prompt}],
                    temperature=0.3
                ),
                timeout=60.0
            )
            
            content = response.choices[0].message.content
            
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
    
    async def _handle_create_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_and_run_script action"""
        import asyncio
        import os
        import tempfile
        
        language = params.get("language", "python")
        code = params.get("code", "")
        should_run = params.get("run", True)
        working_dir = params.get("working_directory", os.path.expanduser("~"))
        
        if not code:
            return {"success": False, "error": "Code is empty"}
        
        ext_map = {"python": ".py", "bash": ".sh", "javascript": ".js", "shell": ".sh"}
        ext = ext_map.get(language.lower(), ".txt")
        
        runner_map = {"python": "python3", "bash": "bash", "javascript": "node", "shell": "bash"}
        runner = runner_map.get(language.lower())
        
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
            
            os.unlink(script_path)
            
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            return {
                "success": process.returncode == 0,
                "output": stdout_str or stderr_str,
                "error": stderr_str if process.returncode != 0 else None
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle read_file action"""
        import os
        
        path = os.path.expanduser(params.get("path", ""))
        encoding = params.get("encoding", "utf-8")
        
        if not path:
            return {"success": False, "error": "Path is empty"}
        
        if not os.path.exists(path):
            return {"success": False, "error": f"File not found: {path}"}
        
        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            
            return {"success": True, "output": content}
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
        
        dangerous_paths = ["/", "/System", "/Library", "/usr", "/bin", "/sbin", os.path.expanduser("~")]
        if path in dangerous_paths:
            return {"success": False, "error": f"Cannot delete protected path: {path}"}
        
        try:
            if os.path.isdir(path):
                if recursive:
                    shutil.rmtree(path)
                else:
                    os.rmdir(path)
            else:
                os.unlink(path)
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
        """Check if command is dangerous"""
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf /*",
            "rm -rf ~",
            "mkfs",
            "dd if=",
            ":(){:|:&};:",
            "chmod -R 777 /",
            "> /dev/sda",
            "mv /* ",
        ]
        
        command_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in command_lower:
                return True
        return False
