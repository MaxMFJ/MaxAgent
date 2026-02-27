"""
Autonomous Agent Core
Implements fully autonomous task execution with structured actions
"""

import asyncio
import json
import os
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
from .safety import validate_action_safe
from tools.router import execute_tool

try:
    from core.task_state_machine import TaskStateMachine, TaskState
    from core.error_model import to_agent_error, AgentError, ErrorCategory
    from core.timeout_policy import get_timeout_policy
except ImportError:
    TaskStateMachine = None  # type: ignore
    TaskState = None  # type: ignore
    to_agent_error = None
    AgentError = None
    ErrorCategory = None
    get_timeout_policy = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy escalation levels for the three-layer defense
# ---------------------------------------------------------------------------
ESCALATION_NORMAL = 0          # No intervention
ESCALATION_FORCE_SWITCH = 1    # Force a different approach (layer 2)
ESCALATION_SKILL_FALLBACK = 2  # Inject skill guidance (layer 3)


AUTONOMOUS_SYSTEM_PROMPT = """你是一个完全自主执行的 macOS Agent，名叫 Chow Duck。你会自动完成用户的任务，无需用户干预。

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

9. **open_app** - 打开应用程序（不可用于发邮件；发邮件必须用 call_tool(mail)）
   ```json
   {"action_type": "open_app", "params": {"app_name": "Safari"}, "reasoning": "..."}
   ```

10. **get_system_info** - 获取系统信息
    ```json
    {"action_type": "get_system_info", "params": {"info_type": "cpu|memory|disk|all"}, "reasoning": "..."}
    ```

11. **call_tool** - 调用已注册的内置工具（推荐用于截图、技能库、邮件等）
   - **发送邮件**（必须用此方式，禁止用 open_app 打开 Mail 应用）：{"action_type": "call_tool", "params": {"tool_name": "mail", "args": {"action": "send", "to": "收件人@example.com", "subject": "主题", "body": "正文"}}, "reasoning": "..."}。系统已配置 SMTP 时直接调用即可。
   - 全屏截图：{"action_type": "call_tool", "params": {"tool_name": "screenshot", "args": {"action": "capture", "area": "full"}}, "reasoning": "..."}
   - **指定应用窗口截图**（如「截图微信窗口」「截 Safari 窗口」）：必须传 app_name，只截该应用窗口：{"action_type": "call_tool", "params": {"tool_name": "screenshot", "args": {"action": "capture", "app_name": "WeChat"}}, "reasoning": "..."}。常见：微信→WeChat，Safari→Safari，Chrome→Google Chrome。
   - 技能库：{"action_type": "call_tool", "params": {"tool_name": "capsule", "args": {"action": "find", "task": "关键词"}}, "reasoning": "..."}
   - macOS 无 screenshot 命令，截图请用 call_tool(tool_name=screenshot) 或 run_shell 时用 **screencapture** 命令。

12. **think** - 思考/分析（不执行任何操作）
    ```json
    {"action_type": "think", "params": {"thought": "分析当前情况..."}, "reasoning": "需要思考下一步"}
    ```

13. **finish** - 完成任务
    ```json
    {"action_type": "finish", "params": {"summary": "任务完成总结", "success": true}, "reasoning": "任务已完成"}
    ```

## 执行规则

1. **每次只输出一个动作**；**禁止只输出纯自然语言**，必须输出上述 JSON 格式（可先简短 reasoning，再跟 ```json ... ``` 块）。
2. **若用户只是打招呼或简单对话**（如「你好」「下午好」「在吗」），也必须用 JSON 回复：输出 `finish`，在 `params.summary` 里写你的回复内容（例如问候+简短说明你能做什么）。不要只回复一段自然文字。
3. **禁止在未执行具体操作前就输出 finish**：若任务需要**打开应用、执行命令、截图、读/写文件**等实际操作，你必须先输出并执行对应动作（如 open_app、run_shell、call_tool 等），等该步骤执行并看到结果后，再根据结果输出 finish。例如「打开微信」必须先输出 `open_app`（params.app_name 为 "WeChat"），等执行成功后再输出 finish；不能直接输出 finish 并写「微信已打开」。
4. **仔细分析上一步的执行结果后再决定下一步**
5. **遇到错误时，分析原因并尝试修复，最多重试 3 次**
6. **任务完成后必须输出 finish 动作**
7. **截图类任务（截屏、截图桌面等）：一旦有一次成功的截图结果，立即输出 finish，不要重复截图**
8. **优先使用批量命令（如 mv *.txt dest/）而不是逐个操作**
9. **保持简洁高效，避免不必要的步骤**
10. **发送邮件：必须使用 call_tool(tool_name=mail)。禁止使用 open_app 打开 Mail 应用来发邮件（Mail 应用限制多、无法可靠自动化）。**

## 安全限制
- 禁止执行 `rm -rf /` 等危险命令
- 禁止修改系统关键文件
- 所有操作都会被记录

{user_context}

现在，根据用户的任务和当前上下文，输出下一步动作的 JSON。"""


def _looks_like_json_or_code(text: str) -> bool:
    """判断内容是否像 JSON 或代码块（避免把未解析成功的 JSON 误当纯文本 finish）。"""
    if not text or len(text) < 10:
        return False
    t = text.strip()
    return (
        t.startswith("{") or t.startswith("[") or
        "```json" in t or "```" in t or
        '"action_type"' in t or '"action_type":' in t
    )


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
            ActionType.CALL_TOOL: self._handle_call_tool,
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
        v3.1: 基于 embedding 相似度或 fallback 到 md5，判断重复失败并返回 escalation 等级。
        阈值从 app_state (ESCALATION_* ) 读取。
        """
        logs = context.action_logs
        if len(logs) < 2:
            return ESCALATION_NORMAL
        try:
            from app_state import (
                ESCALATION_FORCE_AFTER_N,
                ESCALATION_SKILL_AFTER_N,
                ESCALATION_SIMILARITY_THRESHOLD,
            )
        except ImportError:
            ESCALATION_FORCE_AFTER_N, ESCALATION_SKILL_AFTER_N = 2, 3
            ESCALATION_SIMILARITY_THRESHOLD = 0.85

        recent = logs[-5:]
        failed_logs = [log for log in recent if not log.result.success]
        if len(failed_logs) < 2:
            return ESCALATION_NORMAL
        signatures = []
        for log in failed_logs:
            sig_text = f"{log.action.action_type.value}:{log.result.error or str(log.result.output) or ''}"[:300]
            signatures.append(sig_text)

        consecutive_same = 0
        last_sig = signatures[-1]
        try:
            from .vector_store import encode_text_for_similarity
            import numpy as np
            last_emb = encode_text_for_similarity(last_sig)
            if last_emb is not None:
                for i in range(len(signatures) - 1, -1, -1):
                    emb = encode_text_for_similarity(signatures[i])
                    if emb is not None and np.dot(last_emb, emb) >= ESCALATION_SIMILARITY_THRESHOLD:
                        consecutive_same += 1
                    else:
                        break
        except Exception as e:
            logger.debug("Escalation embedding fallback to hash: %s", e)
            last_emb = None

        if last_emb is None:
            hashes = [hashlib.md5(s.encode()).hexdigest()[:10] for s in signatures]
            last_hash = hashes[-1]
            for h in reversed(hashes):
                if h == last_hash:
                    consecutive_same += 1
                else:
                    break

        if consecutive_same >= ESCALATION_SKILL_AFTER_N:
            return ESCALATION_SKILL_FALLBACK
        if consecutive_same >= ESCALATION_FORCE_AFTER_N:
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

    async def _run_mid_loop_reflection(self, context: TaskContext) -> Optional[str]:
        """
        v3.1: 中途轻量反思，返回一句改进建议供下一轮 prompt 注入。
        使用 reflect_llm 或 llm，超时 30s。
        """
        try:
            from app_state import ENABLE_MID_LOOP_REFLECTION
            if not ENABLE_MID_LOOP_REFLECTION:
                return None
        except ImportError:
            pass
        client = self.reflect_llm or self.llm
        if not client:
            return None
        recent = context.action_logs[-5:]
        if len(recent) < 2:
            return None
        steps_text = "\n".join(
            f"  {i+1}. {log.action.action_type.value}: {'成功' if log.result.success else '失败'}"
            + (f" - {log.result.error[:80]}" if log.result.error else "")
            for i, log in enumerate(recent)
        )
        prompt = f"""任务: {context.task_description}

最近步骤:
{steps_text}

请用一两句话给出下一步改进建议（不要重复已失败的做法）。直接输出建议，不要 JSON。"""
        try:
            if get_timeout_policy is not None:
                resp = await get_timeout_policy().with_llm_timeout(
                    client.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=30.0,
                )
            else:
                resp = await asyncio.wait_for(client.chat(messages=[{"role": "user", "content": prompt}]), timeout=30.0)
            content = (resp.get("content") or "").strip()
            return content[:500] if content else None
        except Exception as e:
            logger.debug("Mid-loop reflection failed: %s", e)
            return None

    async def _generate_plan(self, task: str) -> List[str]:
        """
        v3.1 Plan-and-Execute: 生成高层子任务列表，供执行循环参考。
        返回 sub_tasks: List[str]，失败或未启用时返回空列表。
        """
        try:
            from app_state import ENABLE_PLAN_AND_EXECUTE
            if not ENABLE_PLAN_AND_EXECUTE:
                return []
        except ImportError:
            return []
        prompt = f"""请将以下任务拆解为 3-7 个可执行的子步骤，每行一个简短子目标，不要编号不要 JSON。
任务: {task}

子步骤（每行一条）:"""
        try:
            if get_timeout_policy is not None:
                resp = await get_timeout_policy().with_llm_timeout(self.llm.chat(messages=[{"role": "user", "content": prompt}]))
            else:
                resp = await self.llm.chat(messages=[{"role": "user", "content": prompt}])
            content = (resp.get("content") or "").strip()
            lines = [ln.strip() for ln in content.split("\n") if ln.strip() and not ln.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "-", "*"))]
            if not lines:
                lines = [ln.strip().lstrip("0123456789.-) ") for ln in content.split("\n") if ln.strip()][:7]
            return lines[:7] if lines else []
        except Exception as e:
            logger.debug("Plan generation failed: %s", e)
            return []

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
                        f"【指定窗口截图】用户要截的是「{keyword}」窗口，必须用 app_name 参数只截该应用窗口，不要用 area:\"full\"。"
                        f"示例: call_tool params={{\"tool_name\":\"screenshot\",\"args\":{{\"action\":\"capture\",\"app_name\":\"{app_name}\"}}}}"
                    )
                    break
            if not app_window_hint and ("窗口" in task or "某应用" in task or "指定" in task and "截图" in task):
                app_window_hint = (
                    "【指定窗口截图】用户要截的是某个应用的窗口，请在 args 中使用 app_name 参数（如 app_name:\"WeChat\" 表示微信窗口），不要用 area:\"full\" 全屏截图。"
                )
            if app_window_hint:
                parts.append(app_window_hint)
            else:
                parts.append(
                    "【截图】macOS 没有 screenshot 命令。全屏截图请用 call_tool params={\"tool_name\":\"screenshot\",\"args\":{\"action\":\"capture\",\"area\":\"full\"}}；"
                    "或 run_shell: screencapture -x -t png /tmp/screenshot.png"
                )

        # 2) 扫描并注入匹配的 skill/capsule
        try:
            registry = get_capsule_registry()
            if len(registry) > 0:
                capsules = registry.find_capsule_by_task(task, limit=3, min_score=0.7)
                if capsules:
                    parts.append("【匹配技能】以下技能与任务相关，可用 call_tool 执行:")
                    for cap in capsules[:3]:
                        parts.append(
                            f"  - {cap.id}: {cap.description[:60]}… → "
                            f"call_tool(tool_name=\"capsule\", args={{\"action\":\"execute\", \"capsule_id\":\"{cap.id}\", \"inputs\":{{\"task\":\"...\"}}}})"
                        )
        except Exception as e:
            logger.debug(f"Capsule scan for task guidance: {e}")

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
        self._mid_reflection_hint: str = ""  # v3.1 中途反思结果，注入下一轮 prompt
        self._current_plan: List[str] = []  # v3.1 Plan-and-Execute 子任务列表
        self._current_plan_index: int = 0
        
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
                    yield {"type": "plan_created", "task_id": task_id, "sub_tasks": plan}
        except Exception as e:
            logger.debug("Plan-and-Execute init failed: %s", e)
        
        try:
            while True:
                context.current_iteration += 1
                
                # Update adaptive max in context
                if self._stop_policy:
                    context.adaptive_max_iterations = self._stop_policy.current_max_iterations
                
                logger.info(f"Iteration {context.current_iteration}/{context.adaptive_max_iterations}")
                
                # 在线模型网关常对同一 token 限制并发，必须等上一轮返回后再发下一请求。非首轮前等待。
                if context.current_iteration > 1 and self.llm is self.remote_llm:
                    _delay = float(os.environ.get("LLM_REQUEST_DELAY_SECONDS", "2.0"))
                    if _delay > 0:
                        await asyncio.sleep(_delay)
                
                action = await self._generate_action(context)
                
                if action is None:
                    context.retry_count += 1
                    backoff_seconds = min(2 ** context.retry_count, 30)
                    yield {
                        "type": "error",
                        "error": f"无法解析 LLM 输出的动作 (重试 {context.retry_count}/{context.max_retries}，{backoff_seconds}s 后重试)"
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
                        context.stop_reason = "consecutive_failures"
                        context.stop_message = "连续解析失败"
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
                    
                    if state_machine and TaskState is not None:
                        state_machine.transition(TaskState.COMPLETED)
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
                if state_machine and TaskState is not None:
                    state_machine.transition(TaskState.WAITING_TOOL)
                result = await self._execute_action(action)
                if state_machine and TaskState is not None:
                    state_machine.transition(TaskState.RUNNING)
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
                
                chunk = {
                    "type": "action_result",
                    "action_id": action.action_id,
                    "success": result.success,
                    "output": str(result.output)[:500] if result.output else None,
                    "error": result.error,
                    "execution_time_ms": result.execution_time_ms
                }
                # 截图等工具返回 dict 时，单独带上 screenshot_path 供前端展示图片（避免 output 被截断导致 JSON 解析失败）
                if isinstance(result.output, dict):
                    if result.output.get("screenshot_path"):
                        chunk["screenshot_path"] = result.output["screenshot_path"]
                    if result.output.get("image_base64"):
                        chunk["image_base64"] = result.output["image_base64"]
                        chunk["mime_type"] = result.output.get("mime_type", "image/png")
                yield chunk
                
                if not result.success:
                    context.consecutive_action_failures += 1
                    if context.consecutive_action_failures >= context.max_consecutive_action_failures:
                        logger.warning(
                            f"Consecutive action failures reached {context.consecutive_action_failures}, stopping"
                        )
                        context.status = "consecutive_failures"
                        context.stop_reason = "consecutive_failures"
                        context.stop_message = (
                            f"连续 {context.consecutive_action_failures} 次动作执行失败，未完成任务。"
                            f"最后错误: {result.error or '未知'}"
                        )
                        context.completed_at = datetime.now()
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
                            "recommendation": "请检查任务描述或环境（权限、依赖等）后重试。",
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
    
    async def _generate_action(self, context: TaskContext) -> Optional[AgentAction]:
        """Generate the next action using LLM with context enrichment."""
        # Build system prompt with user context (layer 1)
        user_ctx = getattr(self, "_user_context", "")
        system_prompt = AUTONOMOUS_SYSTEM_PROMPT.replace(
            "{user_context}", user_ctx if user_ctx else ""
        )

        # v3.1: 结构化上下文（可选）+ Goal 重述
        try:
            from app_state import USE_SUMMARIZED_CONTEXT, GOAL_RESTATE_EVERY_N
        except ImportError:
            USE_SUMMARIZED_CONTEXT = True
            GOAL_RESTATE_EVERY_N = 6
        if USE_SUMMARIZED_CONTEXT and hasattr(context, "summarize_history_for_llm"):
            context_str = context.summarize_history_for_llm(max_recent=5, max_chars=3500)
        else:
            context_str = context.get_context_for_llm()
        if GOAL_RESTATE_EVERY_N and context.current_iteration > 0 and context.current_iteration % GOAL_RESTATE_EVERY_N == 0:
            context_str = f"【当前目标】原始任务: {context.task_description}\n\n" + context_str
        plan = getattr(self, "_current_plan", []) or []
        plan_index = getattr(self, "_current_plan_index", 0)
        if plan and plan_index < len(plan):
            context_str += f"\n\n【当前建议子目标】{plan[plan_index]}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_str}
        ]
        
        if not context.action_logs:
            first_content = ""
            task_guidance = getattr(self, "_task_guidance", "").strip()
            if task_guidance:
                first_content = f"{task_guidance}\n\n"
            first_content += "开始执行任务。请分析任务并输出第一步动作的 JSON。"
            messages.append({
                "role": "user",
                "content": first_content
            })
        else:
            last_log = context.action_logs[-1]
            result_summary = ""
            if last_log.result.success:
                result_summary = f"上一步执行成功。输出: {str(last_log.result.output)[:300]}"
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
            if mid_hint:
                result_summary += f"\n\n【中途反思建议】{mid_hint}"
                self._mid_reflection_hint = ""

            messages.append({
                "role": "user",
                "content": f"{result_summary}\n\n请分析结果并输出下一步动作的 JSON。"
            })
        
        try:
            import asyncio
            model_info = f"{self.llm.config.provider}/{self.llm.config.model}"
            logger.info(f"Generating action with LLM: {model_info}")
            chat_coro = self.llm.chat(messages=messages)
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(chat_coro)
            else:
                response = await asyncio.wait_for(chat_coro, timeout=120.0)
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
                # 兜底：LLM 返回了纯自然语言（如打招呼回复）时，视为 finish，把整段内容作为 summary 返回
                text = content.strip()[:4000]
                if text and not _looks_like_json_or_code(content):
                    logger.info("Treating plain-text LLM response as finish (summary)")
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
            
            return action
            
        except asyncio.TimeoutError:
            logger.error("LLM request timed out (TimeoutPolicy.llm_timeout or 120s fallback)")
            return None
        except Exception as e:
            logger.error(f"Error generating action: {e}")
            return None
    
    async def _execute_action(self, action: AgentAction) -> ActionResult:
        """Execute a single action. v3.1: 统一安全校验在入口执行。"""
        start_time = time.time()
        ok, err = validate_action_safe(action)
        if not ok:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=err or "安全校验未通过",
                execution_time_ms=int((time.time() - start_time) * 1000),
            )
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
            reflect_coro = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3
            )
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(reflect_coro, timeout=60.0)
            else:
                response = await asyncio.wait_for(reflect_coro, timeout=60.0)
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
    
    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """调用已注册工具（screenshot、capsule、terminal 等），优先使用而非 run_shell 猜测命令。"""
        tool_name = params.get("tool_name", "").strip()
        args = params.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if not tool_name:
            return {"success": False, "error": "call_tool 缺少 tool_name"}
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
        """Check if command is dangerous (delegate to safety module)."""
        ok, _ = validate_action_safe(
            AgentAction(action_type=ActionType.RUN_SHELL, params={"command": command or ""}, reasoning="")
        )
        return not ok
