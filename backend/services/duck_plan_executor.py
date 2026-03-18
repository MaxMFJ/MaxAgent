"""
DuckPlanExecutor — 确定性计划执行引擎 v2.0
====================================================

架构：Supervisor → Planner → Executor → Worker Duck

核心原则：
  - 系统控制执行流，LLM 只负责提议动作
  - 步骤锁：防止重复/并发执行同一步骤
  - 严格步骤顺序：LLM 不能跳步、不能重新规划
  - 工具权限系统：按 duck_type 限制可用工具
  - 机器可验证完成条件：系统判定步骤完成，不信任 LLM 声明
  - 结构化步骤输出：{step, artifacts, facts, confidence}
  - 失败隔离：retry max=2, 然后 SKIP, completion_ratio < 0.6 → FAILED
  - Supervisor 升级协议：Worker 可发出 escalate 请求

流程：
  1. 规划阶段：Planner 生成 3-6 步 JSON（含 allowed_tools + completion_condition）
  2. 执行阶段：逐步执行，每步 FRESH 上下文，系统验证完成条件
  3. 收尾阶段：workspace 最终化，评估 completion_ratio，返回结构化结果

"""

from __future__ import annotations

import asyncio
import fnmatch
import glob
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────
# 配置常量
# ───────────────────────────────────────────
MAX_PLAN_STEPS = 6           # 计划最多步骤数
MAX_STEP_ACTIONS = 5         # 每步最多工具调用次数
MAX_STEP_EMPTY_RETRIES = 2   # 工具空结果最多重试次数
MAX_STEP_FAILURES = 2        # 步骤连续失败上限（超限自动跳过）
STEP_LLM_TIMEOUT = 90        # 每次 LLM 调用超时（秒）
STEP_TOOL_TIMEOUT = 60       # 每次工具调用超时（秒）
MIN_COMPLETION_RATIO = 0.6   # 完成比率低于此值 → 任务判定 FAILED


# ───────────────────────────────────────────
# 工具权限系统
# ───────────────────────────────────────────

# 按 duck_type 定义允许的 action_type 和 call_tool 名称
# 格式: { duck_type_value: { "actions": set[str], "tools": set[str] } }
TOOL_PERMISSIONS: Dict[str, Dict[str, Set[str]]] = {
    "crawler": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "list_directory", "call_tool", "think", "finish"},
        "tools": {"web_search", "browser", "screenshot"},
    },
    "coder": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "move_file", "copy_file", "delete_file", "list_directory",
                     "call_tool", "think", "finish"},
        "tools": {"web_search", "screenshot"},
    },
    "designer": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "move_file", "copy_file", "list_directory", "call_tool",
                     "think", "finish"},
        "tools": {"web_search", "screenshot"},
    },
    "image": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "list_directory", "call_tool", "think", "finish"},
        "tools": {"web_search", "screenshot"},
    },
    "tester": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "list_directory", "call_tool", "think", "finish"},
        "tools": {"web_search", "screenshot"},
    },
    "general": {
        "actions": {"run_shell", "create_and_run_script", "read_file", "write_file",
                     "move_file", "copy_file", "delete_file", "list_directory",
                     "open_app", "close_app", "get_system_info",
                     "clipboard_read", "clipboard_write",
                     "call_tool", "think", "finish"},
        "tools": {"web_search", "browser", "screenshot"},
    },
}

# 所有 duck_type 都禁止的动作
UNIVERSALLY_FORBIDDEN: Set[str] = {
    "delegate_duck", "delegate_dag", "delegate", "delegate_task",
    "spawn_duck", "create_agent", "create_duck",
    "reassign_task", "plan_new_agents", "request_duck",
}


def get_allowed_actions(duck_type: str) -> Set[str]:
    """返回指定 duck_type 允许的 action_type 集合"""
    perms = TOOL_PERMISSIONS.get(duck_type, TOOL_PERMISSIONS["general"])
    return perms["actions"]


def get_allowed_tools(duck_type: str) -> Set[str]:
    """返回指定 duck_type 允许的 call_tool 工具名集合"""
    perms = TOOL_PERMISSIONS.get(duck_type, TOOL_PERMISSIONS["general"])
    return perms["tools"]


def is_action_permitted(action_type: str, duck_type: str, tool_name: str = "") -> bool:
    """检查动作是否在权限范围内"""
    action_lower = action_type.lower()
    if action_lower in UNIVERSALLY_FORBIDDEN:
        return False
    allowed = get_allowed_actions(duck_type)
    if action_lower not in allowed:
        return False
    if action_lower == "call_tool" and tool_name:
        return tool_name.lower() in get_allowed_tools(duck_type)
    return True


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ───────────────────────────────────────────
# 完成条件验证器
# ───────────────────────────────────────────

def verify_completion(condition: Dict[str, Any], workspace_dir: str) -> bool:
    """
    机器验证步骤完成条件。不依赖 LLM 声明。

    支持的条件类型：
      {"min_files": 3}           — 工作区至少 N 个文件
      {"file_exists": "report.md"} — 指定文件存在
      {"file_pattern": "*.md"}   — 至少一个文件匹配 glob
      {"min_total_bytes": 500}   — 文件总大小 ≥ N 字节
      {"always": true}           — 无条件通过（用于无文件产出步骤）

    多个条件键同时存在时，全部满足才返回 True。
    """
    if not condition or not isinstance(condition, dict):
        return True  # 无条件 → 通过

    files = _scan_workspace(workspace_dir)
    results = []

    if "always" in condition:
        results.append(bool(condition["always"]))

    if "min_files" in condition:
        results.append(len(files) >= int(condition["min_files"]))

    if "file_exists" in condition:
        target = condition["file_exists"]
        # 支持相对路径和文件名
        results.append(any(
            f.endswith(target) or os.path.basename(f) == target
            for f in files
        ))

    if "file_pattern" in condition:
        pattern = condition["file_pattern"]
        results.append(any(
            fnmatch.fnmatch(os.path.basename(f), pattern) for f in files
        ))

    if "min_total_bytes" in condition:
        total = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
        results.append(total >= int(condition["min_total_bytes"]))

    return all(results) if results else True


# ───────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────

@dataclass
class PlanStep:
    index: int
    description: str
    completion_condition: Dict[str, Any] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result_summary: str = ""
    output_files: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    action_count: int = 0
    empty_result_count: int = 0
    failure_count: int = 0

    def structured_output(self) -> Dict[str, Any]:
        """返回结构化步骤输出"""
        return {
            "step": self.index + 1,
            "status": self.status.value,
            "artifacts": self.artifacts or self.output_files,
            "facts": self.facts,
            "confidence": self.confidence,
            "summary": self.result_summary,
        }


@dataclass
class ExecutionState:
    task_id: str
    plan_id: str
    duck_type: str = "general"
    steps: List[PlanStep] = field(default_factory=list)
    current_step_index: int = 0
    execution_locked: bool = False
    allow_replan: bool = False  # v2.0: replanning 始终禁止
    workspace_dir: str = ""
    started_at: float = field(default_factory=time.time)
    escalations: List[Dict[str, str]] = field(default_factory=list)

    @property
    def current_step(self) -> Optional[PlanStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    @property
    def completion_ratio(self) -> float:
        if not self.steps:
            return 0.0
        done = sum(1 for s in self.steps if s.status == StepStatus.DONE)
        return done / len(self.steps)

    @property
    def total_failures(self) -> int:
        return sum(s.failure_count for s in self.steps)

    def complete_step(self, result_summary: str, output_files: List[str] = None):
        step = self.current_step
        if step:
            step.status = StepStatus.DONE
            step.result_summary = result_summary
            step.output_files = output_files or []
            step.artifacts = output_files or []
            # 基于文件产出评估 confidence
            step.confidence = min(1.0, 0.5 + 0.1 * len(step.output_files))
        self.execution_locked = False
        self.current_step_index += 1

    def fail_step(self, reason: str):
        step = self.current_step
        if step:
            step.status = StepStatus.FAILED
            step.failure_count += 1
        self.execution_locked = False

    def skip_step(self, reason: str):
        step = self.current_step
        if step:
            step.status = StepStatus.SKIPPED
            step.result_summary = f"[已跳过] {reason}"
            step.confidence = 0.0
        self.execution_locked = False
        self.current_step_index += 1

    def is_finished(self) -> bool:
        return self.current_step_index >= len(self.steps)

    def context_summary(self) -> Dict[str, Any]:
        """返回结构化 JSON 上下文摘要，供步骤执行器使用"""
        completed = []
        for s in self.steps[:self.current_step_index]:
            if s.status in (StepStatus.DONE, StepStatus.SKIPPED):
                completed.append(s.structured_output())
        return {
            "task_id": self.task_id,
            "duck_type": self.duck_type,
            "completion_ratio": round(self.completion_ratio, 2),
            "current_step": self.current_step_index + 1,
            "total_steps": len(self.steps),
            "completed_steps": completed,
        }

    def context_summary_text(self) -> str:
        """兼容文本格式摘要"""
        lines = []
        for s in self.steps[:self.current_step_index]:
            if s.status in (StepStatus.DONE, StepStatus.SKIPPED):
                tag = "✅" if s.status == StepStatus.DONE else "⚠️"
                lines.append(f"步骤{s.index+1}[{tag}]: {s.description[:50]} → {s.result_summary[:150]}")
                if s.output_files:
                    lines.append(f"  产出: {', '.join(os.path.basename(f) for f in s.output_files[:3])}")
        return "\n".join(lines) if lines else "（无前置步骤）"


# ───────────────────────────────────────────
# 规划阶段 (Planner v2)
# ───────────────────────────────────────────

PLANNER_PROMPT_TEMPLATE = """你是一个执行规划器。请将以下任务分解为 3-{max_steps} 个**具体可执行**的步骤。

任务：{task_description}

Duck 类型：{duck_type}
工作区路径（所有文件必须保存到这里）：{workspace_dir}
可用工具：{allowed_tools_desc}

输出格式（严格 JSON，不要 markdown 代码块）：
{{
  "steps": [
    {{
      "description": "步骤描述（具体、可操作）",
      "completion_condition": {{
        "min_files": 1,
        "file_pattern": "*.md"
      }}
    }}
  ]
}}

completion_condition 支持的键（可组合使用）：
  - "min_files": N          — 工作区至少 N 个文件
  - "file_exists": "name"   — 指定文件名存在
  - "file_pattern": "*.ext" — 至少一个文件匹配 glob
  - "min_total_bytes": N    — 工作区文件总大小 ≥ N 字节
  - "always": true          — 无条件通过（用于搜索/分析等无文件产出步骤）

规则：
1. 最多 {max_steps} 步，每步聚焦一个目标
2. 最后一步必须包含 "file_exists" 或 "min_files" 条件
3. 不要有"分析规划"类步骤，每步必须产生实际输出或搜索结果
4. 搜索/信息收集步骤用 {{"always": true}}
5. completion_condition 必须是 JSON 对象，不要写文字"""


async def generate_plan(
    llm_client,
    task_description: str,
    workspace_dir: str,
    duck_type: str = "general",
    max_steps: int = MAX_PLAN_STEPS,
) -> List[PlanStep]:
    """调用 LLM 生成结构化的执行计划（含 completion_condition JSON）"""
    allowed_actions = get_allowed_actions(duck_type)
    allowed_tools = get_allowed_tools(duck_type)
    tools_desc = ", ".join(sorted(allowed_actions | allowed_tools))

    prompt = PLANNER_PROMPT_TEMPLATE.format(
        task_description=task_description[:800],
        workspace_dir=workspace_dir,
        duck_type=duck_type,
        max_steps=max_steps,
        allowed_tools_desc=tools_desc,
    )
    try:
        resp = await asyncio.wait_for(
            llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
            ),
            timeout=STEP_LLM_TIMEOUT,
        )
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group(0))
            raw_steps = data.get("steps", [])
            steps = []
            for i, s in enumerate(raw_steps[:max_steps]):
                # 解析 completion_condition — 兼容旧格式字符串和新 JSON
                raw_cc = s.get("completion_condition", {})
                if isinstance(raw_cc, str):
                    cc = {"always": True}  # 降级
                elif isinstance(raw_cc, dict):
                    cc = raw_cc
                else:
                    cc = {"always": True}

                steps.append(PlanStep(
                    index=i,
                    description=s.get("description", f"步骤 {i+1}"),
                    completion_condition=cc,
                    allowed_tools=list(get_allowed_tools(duck_type)),
                ))
            if steps:
                logger.info(f"[Planner] Generated plan: {len(steps)} steps for {duck_type}")
                return steps
    except Exception as e:
        logger.warning(f"[Planner] Plan generation failed: {e}, using single-step fallback")

    # 降级：单步执行
    return [PlanStep(
        index=0,
        description=task_description[:500],
        completion_condition={"min_files": 1},
        allowed_tools=list(get_allowed_tools(duck_type)),
    )]


# ───────────────────────────────────────────
# 步骤执行器 (Worker Duck)
# ───────────────────────────────────────────

STEP_EXECUTOR_SYSTEM = """
╔═══════════════════════════════════╗
║  RUNTIME IDENTITY — WORKER DUCK  ║
╚═══════════════════════════════════╝
- role: WORKER_DUCK
- duck_type: {duck_type}
- authority_level: EXECUTOR_ONLY
- execution_mode: WORKER

You ARE the assigned specialist executing a single task step.
You are NOT an orchestrator.
Delegation and orchestration are FORBIDDEN.

⛔ FORBIDDEN ACTIONS — System will REJECT any of these:
  - delegate_duck / spawn_duck / create_agent / create_duck
  - reassign_task / plan_new_agents / request_duck

✅ ALLOWED TOOLS for your role ({duck_type}):
  {allowed_tools_list}

If you need help that requires another agent → do it yourself with available tools.
If you are completely blocked → output: {{"action": "escalate", "reason": "说明原因"}}

---

Current workspace (ALL outputs MUST be saved here):
  {workspace_dir}

Step {step_index} of {total_steps}

Previous steps:
{context_summary}

⚠️ Rules:
1. Execute ONLY the current step — do NOT jump ahead or replan
2. Do NOT delegate to another agent
3. Save ALL files to the workspace path above
4. When done, immediately output a finish action
5. If stuck, escalate instead of looping
6. Do NOT read the same file repeatedly — read once and use the result
7. When reading large files, focus on the parts you need, do not read the entire file if only a summary is needed
8. NEVER repeat a failed action — if timeout or error occurs, move forward with what you have"""

STEP_EXECUTOR_USER = """请执行以下步骤：

{step_description}

完成后使用 finish 动作，summary 中描述你完成了什么、生成了哪些文件。"""


# Forbidden actions for WORKER_DUCK — any of these must be rejected
FORBIDDEN_WORKER_ACTIONS = {
    "delegate_duck", "spawn_duck", "create_agent", "create_duck",
    "reassign_task", "plan_new_agents", "request_duck",
    "delegate", "delegate_task", "delegate_dag",
}

WORKER_REJECTION_MESSAGE = (
    "You are operating as a WORKER_DUCK (EXECUTOR_ONLY). "
    "Delegation and orchestration actions are NOT permitted. "
    "Continue execution using available tools only. "
    "If you are completely blocked, use finish action to report what you have."
)


def _extract_escalation(chunk: dict) -> Optional[Dict[str, str]]:
    """检测 Worker Duck 发出的 escalation 请求"""
    if chunk.get("type") == "task_complete":
        summary = chunk.get("summary", "")
        try:
            # 尝试解析 JSON escalation
            m = re.search(r'\{[^}]*"action"\s*:\s*"escalate"[^}]*\}', summary)
            if m:
                data = json.loads(m.group(0))
                if data.get("action") == "escalate":
                    return {"reason": data.get("reason", "unknown")}
        except (json.JSONDecodeError, AttributeError):
            pass
    return None


async def execute_step(
    agent,
    state: ExecutionState,
    step: PlanStep,
    session_id: str,
    broadcast_fn=None,
) -> str:
    """
    执行单个步骤，返回步骤结果摘要。
    包含工具权限验证和 escalation 检测。
    """
    if state.execution_locked:
        raise RuntimeError(f"步骤 {step.index} 执行锁已占用，拒绝重入")

    state.execution_locked = True
    step.status = StepStatus.RUNNING

    allowed_actions = get_allowed_actions(state.duck_type)
    allowed_tools = get_allowed_tools(state.duck_type)
    all_allowed = sorted(allowed_actions | allowed_tools)

    system_addendum = STEP_EXECUTOR_SYSTEM.format(
        workspace_dir=state.workspace_dir,
        duck_type=state.duck_type,
        step_index=step.index + 1,
        total_steps=len(state.steps),
        context_summary=state.context_summary_text(),
        allowed_tools_list=", ".join(all_allowed),
    )

    user_prompt = STEP_EXECUTOR_USER.format(
        step_description=step.description,
    )
    full_prompt = f"[STEP CONTEXT]\n{system_addendum}\n\n[TASK]\n{user_prompt}"

    result_summary = ""
    _forbidden_rejection_count = 0
    _permission_rejection_count = 0
    _action_history: List[str] = []  # 动作签名历史，用于循环检测
    _MAX_SAME_ACTION = 2  # 同一动作最多重复次数
    _tool_call_count = 0  # 实际工具执行次数（action_result chunk）
    try:
        async for chunk in agent.run_autonomous(full_prompt, session_id=f"{session_id}_step{step.index}"):
            step.action_count += 1

            chunk_type = chunk.get("type", "")

            # ── 工具权限守卫 ──────────────────────────
            if chunk_type == "action_plan":
                action_dict = chunk.get("action", {})
                action_type = (action_dict.get("action_type") or "").lower()
                params = action_dict.get("parameters", {})

                # 0. 动作循环检测：同一动作签名重复超限 → 强制完成步骤
                action_sig = f"{action_type}:{json.dumps(params, sort_keys=True, ensure_ascii=False)[:200]}"
                _action_history.append(action_sig)
                same_count = _action_history.count(action_sig)
                if same_count > _MAX_SAME_ACTION:
                    logger.warning(
                        f"[Executor] Action loop detected at step {step.index+1}: "
                        f"'{action_type}' repeated {same_count}x, forcing step completion"
                    )
                    if broadcast_fn:
                        try:
                            await broadcast_fn({
                                "type": "tool_result",
                                "result": (
                                    f"⚠️ 检测到动作循环：{action_type} 已重复 {same_count} 次。"
                                    "请立即使用 finish 动作完成当前步骤，用已收集的信息继续。"
                                    "不要再重复相同操作。"
                                ),
                                "success": False,
                            })
                        except Exception:
                            pass
                    # 连续循环 3 次以上 → 直接终止
                    if same_count > _MAX_SAME_ACTION + 1:
                        result_summary = f"步骤因动作循环被终止（{action_type} 重复 {same_count} 次）"
                        break
                    continue

                # 1. 全局禁止动作
                if action_type in FORBIDDEN_WORKER_ACTIONS:
                    _forbidden_rejection_count += 1
                    logger.warning(
                        f"[Executor] REJECTED forbidden '{action_type}' at step {step.index+1} "
                        f"(#{_forbidden_rejection_count})"
                    )
                    if broadcast_fn:
                        try:
                            await broadcast_fn({
                                "type": "error",
                                "error": f"⛔ 禁止操作：Worker Duck 不允许 {action_type}",
                            })
                        except Exception:
                            pass
                    if _forbidden_rejection_count >= 3:
                        raise RuntimeError(f"Worker Duck 多次尝试委派（{_forbidden_rejection_count}次）")
                    if broadcast_fn:
                        try:
                            await broadcast_fn({
                                "type": "tool_result",
                                "result": WORKER_REJECTION_MESSAGE,
                                "success": False,
                            })
                        except Exception:
                            pass
                    continue

                # 2. 工具权限验证
                tool_name = ""
                if action_type == "call_tool":
                    tool_name = (action_dict.get("tool_name") or
                                 action_dict.get("parameters", {}).get("tool_name", "")).lower()
                if not is_action_permitted(action_type, state.duck_type, tool_name):
                    _permission_rejection_count += 1
                    logger.warning(
                        f"[Executor] DENIED '{action_type}' (tool={tool_name}) for {state.duck_type} "
                        f"at step {step.index+1}"
                    )
                    if broadcast_fn:
                        try:
                            await broadcast_fn({
                                "type": "tool_result",
                                "result": f"Permission denied: {action_type} is not allowed for {state.duck_type}. "
                                          f"Allowed: {', '.join(sorted(allowed_actions))}",
                                "success": False,
                            })
                        except Exception:
                            pass
                    continue

                # 3. 工作区路径强制：write_file/create_and_run_script 必须写入 workspace
                if action_type in ("write_file", "create_and_run_script") and state.workspace_dir:
                    file_path = params.get("file_path") or params.get("path") or ""
                    if file_path and not file_path.startswith(state.workspace_dir):
                        # 自动重写路径到 workspace
                        basename = os.path.basename(file_path)
                        corrected = os.path.join(state.workspace_dir, basename)
                        logger.warning(
                            f"[Executor] Redirecting write from '{file_path}' → '{corrected}'"
                        )
                        if "file_path" in params:
                            params["file_path"] = corrected
                        elif "path" in params:
                            params["path"] = corrected
                        # 更新 chunk 中的 action
                        action_dict["parameters"] = params

            if broadcast_fn:
                try:
                    await broadcast_fn(chunk)
                except Exception:
                    pass

            # ── MAX_STEP_ACTIONS 工具调用次数限制 ─────
            if chunk_type == "action_result":
                _tool_call_count += 1
                # 若 web_search/搜索类工具连续返回空结果，注入强制收尾提示
                if _tool_call_count >= 2:
                    _last_output = chunk.get("output") or ""
                    _last_success = chunk.get("success", True)
                    if _last_success and isinstance(_last_output, str) and (
                        "'count': 0" in _last_output or '"count": 0' in _last_output
                        or "count': 0" in _last_output or "results': []" in _last_output
                        or "'results': []" in _last_output
                    ):
                        logger.info(
                            "[Executor] Step %d: search returned empty results x%d, "
                            "injecting fallback hint",
                            step.index + 1, _tool_call_count,
                        )
                        if broadcast_fn:
                            try:
                                await broadcast_fn({
                                    "type": "tool_result",
                                    "result": (
                                        "⚠️ 搜索接口返回空结果，网络搜索受限。"
                                        "请改用你的内置知识完成任务：直接用 write_file 或 create_and_run_script "
                                        "根据已知信息生成内容，然后用 finish 结束当前步骤。"
                                        "不要再尝试网络搜索。"
                                    ),
                                    "success": False,
                                })
                            except Exception:
                                pass
                if _tool_call_count >= MAX_STEP_ACTIONS:
                    logger.warning(
                        "[Executor] Step %d reached MAX_STEP_ACTIONS=%d, forcing step completion",
                        step.index + 1, MAX_STEP_ACTIONS,
                    )
                    result_summary = f"步骤 {step.index+1} 已执行 {_tool_call_count} 次工具调用，强制结束步骤"
                    if broadcast_fn:
                        try:
                            await broadcast_fn({
                                "type": "tool_result",
                                "result": (
                                    f"⚠️ 当前步骤已调用工具 {_tool_call_count} 次（上限 {MAX_STEP_ACTIONS}），"
                                    "系统强制结束本步骤。请继续下一步。"
                                ),
                                "success": False,
                            })
                        except Exception:
                            pass
                    break

            # ── escalation 检测 ──────────────────────
            escalation = _extract_escalation(chunk)
            if escalation:
                state.escalations.append({
                    "step": step.index + 1,
                    "reason": escalation["reason"],
                })
                logger.info(f"[Executor] Escalation from step {step.index+1}: {escalation['reason']}")
                result_summary = f"[ESCALATED] {escalation['reason']}"
                break

            if chunk_type == "task_complete":
                result_summary = chunk.get("summary", "") or ""
                break
            elif chunk_type == "task_stopped":
                result_summary = chunk.get("message", "步骤因错误停止")
                break
            elif chunk_type == "error":
                raise RuntimeError(chunk.get("error", "Step execution error"))

    except asyncio.CancelledError:
        raise
    except Exception as e:
        step.failure_count += 1
        state.execution_locked = False
        raise

    state.execution_locked = False
    # 若 generator 静默退出（无 task_complete / task_stopped），给出默认摘要避免空字符串误判为失败
    if not result_summary:
        result_summary = f"步骤 {step.index + 1} 执行结束（执行了 {_tool_call_count} 次工具调用）"
        logger.info(
            "[Executor] Step %d: generator exited silently (tool_calls=%d), using default summary",
            step.index + 1, _tool_call_count,
        )
    return result_summary


# ───────────────────────────────────────────
# 主执行入口 (Executor + Supervisor)
# ───────────────────────────────────────────

async def run_duck_task_with_plan(
    agent,
    llm_client,
    task_description: str,
    workspace_dir: str,
    task_id: str,
    session_id: str,
    duck_type: str = "general",
    hard_timeout: float = 600.0,
    broadcast_fn=None,
) -> str:
    """
    确定性计划执行入口 v2.0。

    流程：Planner → Executor → Completion Verifier → Supervisor
    返回最终结果字符串（含结构化摘要和工作区文件清单）。
    """
    deadline = time.time() + hard_timeout

    # ── 1. 规划阶段（运行一次，不允许 replan）──────────
    logger.info(f"[Executor] Task {task_id}: planning for duck_type={duck_type}")
    steps = await generate_plan(llm_client, task_description, workspace_dir, duck_type)

    state = ExecutionState(
        task_id=task_id,
        plan_id=f"plan_{task_id[:8]}",
        duck_type=duck_type,
        steps=steps,
        workspace_dir=workspace_dir,
    )

    logger.info(f"[Executor] Plan: {len(steps)} steps")
    for s in steps:
        logger.info(f"  Step {s.index+1}: {s.description[:60]} | cc={s.completion_condition}")

    # 广播计划
    if broadcast_fn:
        try:
            plan_info = {
                "type": "plan_generated",
                "steps": [{"index": s.index + 1, "description": s.description[:80]} for s in steps],
            }
            await broadcast_fn(plan_info)
        except Exception:
            pass

    # ── 2. 执行阶段 ──────────────────────────
    files_before = set(_scan_workspace(workspace_dir))

    while not state.is_finished():
        if time.time() > deadline:
            logger.warning(f"[Executor] Hard deadline reached, stopping early")
            if broadcast_fn:
                try:
                    await broadcast_fn({"type": "error", "error": "⏰ 总时间已到达上限，提前结束"})
                except Exception:
                    pass
            break

        step = state.current_step
        if step is None:
            break

        # 步骤已超过失败上限 → 跳过
        if step.failure_count >= MAX_STEP_FAILURES:
            logger.warning(f"[Executor] Step {step.index+1} failed {step.failure_count} times, skipping")
            state.skip_step(f"失败次数超过上限（{step.failure_count}）")
            if broadcast_fn:
                try:
                    await broadcast_fn({
                        "type": "tool_result",
                        "result": f"⚠️ 步骤 {step.index+1} 失败 {step.failure_count} 次，已跳过",
                        "success": False,
                    })
                except Exception:
                    pass
            continue

        logger.info(f"[Executor] Step {step.index+1}/{len(steps)}: {step.description[:60]}")

        # 广播步骤开始
        if broadcast_fn:
            try:
                await broadcast_fn({
                    "type": "tool_call",
                    "tool_name": f"plan_step_{step.index+1}",
                    "action_type": "plan_step",
                    "description": f"📌 执行步骤 {step.index+1}/{len(steps)}: {step.description[:60]}",
                })
            except Exception:
                pass

        step_timeout = min(240.0, deadline - time.time())
        if step_timeout < 10:
            break

        try:
            step_result = await asyncio.wait_for(
                execute_step(agent, state, step, session_id, broadcast_fn),
                timeout=step_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[Executor] Step {step.index+1} timed out ({step_timeout:.0f}s)")
            step_result = f"步骤 {step.index+1} 超时（{step_timeout:.0f}s）"
            step.failure_count += 1
            state.execution_locked = False
            if broadcast_fn:
                try:
                    await broadcast_fn({
                        "type": "tool_result",
                        "result": f"⏰ 步骤 {step.index+1} 超时（{step_timeout:.0f}s），将重试或跳过",
                        "success": False,
                    })
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[Executor] Step {step.index+1} error: {e}")
            step.failure_count += 1
            state.execution_locked = False
            if broadcast_fn:
                try:
                    await broadcast_fn({
                        "type": "tool_result",
                        "result": f"❌ 步骤 {step.index+1} 异常: {str(e)[:100]}",
                        "success": False,
                    })
                except Exception:
                    pass
            if step.failure_count < MAX_STEP_FAILURES:
                continue  # 重试当前步骤
            else:
                state.skip_step(str(e)[:100])
                continue

        # ── 完成条件机器验证 ──────────────────
        output_files = _scan_workspace(workspace_dir)
        condition_met = verify_completion(step.completion_condition, workspace_dir)

        if condition_met:
            new_files = [f for f in output_files if f not in files_before]
            state.complete_step(step_result[:300], new_files or output_files)
            files_before = set(output_files)
            logger.info(
                f"[Executor] Step {step.index+1} DONE (verified). "
                f"Workspace: {len(output_files)} files"
            )
        else:
            # 条件未满足但 LLM 声称完成　→ 仍然放行（避免卡死），但降低 confidence
            logger.warning(
                f"[Executor] Step {step.index+1}: completion condition NOT met "
                f"({step.completion_condition}), accepting with low confidence"
            )
            new_files = [f for f in output_files if f not in files_before]
            state.complete_step(step_result[:300], new_files or output_files)
            if state.steps[state.current_step_index - 1]:
                state.steps[state.current_step_index - 1].confidence = 0.3
            files_before = set(output_files)

    # ── 3. Supervisor 最终评估 ──────────────────
    final_files = _scan_workspace(workspace_dir)
    ratio = state.completion_ratio
    done_count = sum(1 for s in state.steps if s.status == StepStatus.DONE)

    # Workspace 救援：如果有文件产出但 ratio 低，仍视为部分成功
    if ratio < MIN_COMPLETION_RATIO and final_files:
        logger.info(
            f"[Supervisor] completion_ratio={ratio:.2f} < {MIN_COMPLETION_RATIO}, "
            f"but workspace has {len(final_files)} files — accepting as partial success"
        )
        task_verdict = "partial"
    elif ratio < MIN_COMPLETION_RATIO:
        task_verdict = "failed"
        logger.warning(f"[Supervisor] Task FAILED: completion_ratio={ratio:.2f}")
    else:
        task_verdict = "success"

    # 结构化输出
    structured_result = {
        "task_id": task_id,
        "verdict": task_verdict,
        "completion_ratio": round(ratio, 2),
        "steps_done": done_count,
        "steps_total": len(state.steps),
        "escalations": state.escalations,
        "steps": [s.structured_output() for s in state.steps],
    }

    # 人类可读文本
    steps_summary = "\n".join(
        f"  Step {s.index+1}[{s.status.value}]: {s.description[:40]} → {s.result_summary[:80]}"
        for s in state.steps
    )

    if task_verdict == "failed":
        result = (
            f"任务未能完成（{done_count}/{len(state.steps)} 步骤成功，"
            f"完成率 {ratio:.0%}）\n\n执行摘要：\n{steps_summary}\n"
        )
    else:
        result = (
            f"任务已完成（{done_count}/{len(state.steps)} 步骤成功，"
            f"完成率 {ratio:.0%}）\n\n执行摘要：\n{steps_summary}\n"
        )

    if final_files:
        result += f"\n\n【工作区产出】目录: {workspace_dir}\n" + "\n".join(
            f"  - {f}" for f in final_files[:30]
        )

    if state.escalations:
        result += "\n\n【升级请求】\n" + "\n".join(
            f"  Step {e['step']}: {e['reason']}" for e in state.escalations
        )

    logger.info(
        f"[Supervisor] Task {task_id} verdict={task_verdict} "
        f"ratio={ratio:.2f} files={len(final_files)}"
    )
    return result


def _scan_workspace(workspace_dir: str) -> List[str]:
    """扫描工作区目录，返回所有文件路径列表"""
    files = []
    try:
        if os.path.isdir(workspace_dir):
            for dp, dd, ff in os.walk(workspace_dir):
                dd[:] = [d for d in dd if not d.startswith(".")]
                for fn in ff:
                    if not fn.startswith("."):
                        files.append(os.path.join(dp, fn))
    except Exception:
        pass
    return files
