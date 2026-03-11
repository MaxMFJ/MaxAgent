"""
Unified Execution Policy & Step Schema
========================================
Chat 和 Autonomous 不再是不同系统，
而是同一个 Runtime + 不同 ExecutionPolicy。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# Execution Policy
# ──────────────────────────────────────────────

class PolicyMode(str, Enum):
    """执行策略模式"""
    CHAT = "chat"                # 单/少步, 流式, 高交互
    AUTONOMOUS = "autonomous"    # 多步, 自主, 低交互
    HYBRID = "hybrid"            # 适应性: 简单任务单步，复杂任务多步


@dataclass
class ExecutionPolicy:
    """
    控制 Agent Runtime 行为的策略参数。
    Chat 和 Autonomous 只是不同的 Policy 配置。
    """
    mode: PolicyMode = PolicyMode.CHAT

    # 循环控制
    max_steps: int = 50               # 最多执行步数
    min_steps_before_finish: int = 0   # 完成前最少步数 (Auto 至少 1 步)
    allow_self_retry: bool = True      # 允许自动重试失败操作
    max_retries_per_step: int = 3

    # 流式输出
    streaming: bool = True             # 是否流式输出 LLM 响应
    stream_tool_logs: bool = True      # 是否流式输出工具执行日志

    # 用户交互
    user_visible: bool = True          # 执行过程对用户可见
    ask_confirmation: str = "never"    # "always" | "high_risk" | "never"
    interruption_allowed: bool = True  # 允许用户中断

    # 停止策略
    enable_adaptive_stop: bool = False # 自适应停止
    max_tokens: int = 100000           # token 预算
    max_time_seconds: int = 600        # 时间预算

    # 高级功能
    enable_model_selection: bool = False  # 智能模型选择
    enable_reflection: bool = False       # 事后反思
    enable_planning: bool = False         # 先生成计划再执行
    enable_mid_reflection: bool = False   # 中途反思
    enable_phase_tracking: bool = True    # Gather/Act/Verify 阶段追踪

    # v3.5 新架构
    enable_observation: bool = True       # 观察循环
    enable_confidence: bool = True        # 置信度评估
    enable_error_tracking: bool = True    # 错误分类追踪
    enable_circuit_breaker: bool = False  # 熔断器
    enable_goal_tracking: bool = False    # 目标进度追踪
    enable_runtime_intel: bool = False    # 运行时智能
    enable_evidence: bool = False         # 证据收集

    @classmethod
    def chat(cls) -> ExecutionPolicy:
        """Chat 模式: 单步/少步, 流式, 高交互"""
        return cls(
            mode=PolicyMode.CHAT,
            max_steps=5,
            min_steps_before_finish=0,
            streaming=True,
            stream_tool_logs=True,
            user_visible=True,
            ask_confirmation="never",
            interruption_allowed=True,
            enable_adaptive_stop=False,
            enable_model_selection=False,
            enable_reflection=False,
            enable_planning=False,
            enable_observation=True,
            enable_confidence=False,
            enable_error_tracking=True,
            enable_circuit_breaker=False,
            enable_goal_tracking=False,
            enable_runtime_intel=False,
            enable_evidence=False,
        )

    @classmethod
    def autonomous(
        cls,
        max_iterations: int = 50,
        max_tokens: int = 100000,
        max_time_seconds: int = 600,
    ) -> ExecutionPolicy:
        """Autonomous 模式: 多步, 自主, 低交互"""
        return cls(
            mode=PolicyMode.AUTONOMOUS,
            max_steps=max_iterations,
            min_steps_before_finish=1,
            streaming=False,
            stream_tool_logs=False,
            user_visible=True,  # 仍然可被观察
            ask_confirmation="high_risk",
            interruption_allowed=True,
            allow_self_retry=True,
            enable_adaptive_stop=True,
            max_tokens=max_tokens,
            max_time_seconds=max_time_seconds,
            enable_model_selection=True,
            enable_reflection=True,
            enable_planning=True,
            enable_mid_reflection=True,
            enable_observation=True,
            enable_confidence=True,
            enable_error_tracking=True,
            enable_circuit_breaker=True,
            enable_goal_tracking=True,
            enable_runtime_intel=True,
            enable_evidence=True,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "max_steps": self.max_steps,
            "streaming": self.streaming,
            "enable_adaptive_stop": self.enable_adaptive_stop,
            "enable_model_selection": self.enable_model_selection,
            "enable_planning": self.enable_planning,
            "enable_reflection": self.enable_reflection,
        }


# ──────────────────────────────────────────────
# Unified Step Schema
# ──────────────────────────────────────────────

class StepStatus(str, Enum):
    PLANNED = "planned"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class StepObservation:
    """Step 执行后的观察"""
    env_changes: List[str] = field(default_factory=list)
    ui_snapshot: str = ""
    verify_note: str = ""
    anomalies: List[str] = field(default_factory=list)

    def for_llm(self, max_chars: int = 400) -> str:
        parts = []
        if self.env_changes:
            parts.append("变化: " + "; ".join(self.env_changes))
        if self.verify_note:
            parts.append(f"验证: {self.verify_note}")
        if self.anomalies:
            parts.append("异常: " + "; ".join(self.anomalies))
        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    def has_content(self) -> bool:
        return bool(self.env_changes or self.verify_note or self.anomalies)


@dataclass
class UnifiedStep:
    """
    统一的步骤记录 — Chat 和 Autonomous 完全一致。
    每个 Step = 一次 LLM → 工具执行 → 观察 的完整周期。
    """
    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    iteration: int = 0

    # 目标
    goal: str = ""                    # 此步骤的子目标 (from LLM reasoning)

    # 动作
    action_type: str = ""             # 动作类型 (run_shell, write_file, etc.)
    action_params: Dict[str, Any] = field(default_factory=dict)

    # 结果
    status: StepStatus = StepStatus.PLANNED
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0

    # 元数据
    confidence: float = 1.0           # 执行前的置信度
    state_diff: Dict[str, Any] = field(default_factory=dict)  # 环境变化
    observation: Optional[StepObservation] = None

    # 时间戳
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def complete(self, success: bool, output: Any = None, error: str = None) -> None:
        self.success = success
        self.output = output
        self.error = error
        self.status = StepStatus.SUCCESS if success else StepStatus.FAILED
        self.completed_at = time.time()
        if self.created_at:
            self.execution_time_ms = int((self.completed_at - self.created_at) * 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "iteration": self.iteration,
            "goal": self.goal,
            "action_type": self.action_type,
            "status": self.status.value,
            "success": self.success,
            "output": str(self.output)[:300] if self.output else None,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "confidence": self.confidence,
        }

    def for_llm(self, max_output_chars: int = 200) -> str:
        """Compact representation for LLM context injection."""
        status_icon = "✓" if self.success else "✗"
        parts = [f"[{status_icon}] {self.action_type}"]
        if self.goal:
            parts[0] += f" ({self.goal})"
        if self.output:
            out_str = str(self.output)[:max_output_chars]
            parts.append(f"  → {out_str}")
        if self.error:
            parts.append(f"  ✗ {self.error[:100]}")
        if self.observation and self.observation.has_content():
            parts.append(f"  📋 {self.observation.for_llm(200)}")
        return "\n".join(parts)


# ──────────────────────────────────────────────
# Task State (统一的任务状态)
# ──────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    PAUSED = "paused"


@dataclass
class UnifiedTaskState:
    """
    统一的任务状态 — 替代 TaskContext + ConversationContext 的功能子集。
    保留对两者的向后兼容。
    """
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    session_id: str = "default"
    description: str = ""
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy.chat)

    # 步骤记录
    steps: List[UnifiedStep] = field(default_factory=list)
    current_iteration: int = 0

    # 状态
    status: TaskStatus = TaskStatus.PENDING
    stop_reason: str = ""
    final_result: str = ""

    # Token 追踪
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    # 产出追踪
    key_artifacts: List[Dict[str, Any]] = field(default_factory=list)

    # 时间
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    # ── Convenience ──

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.steps if s.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)

    @property
    def success_rate(self) -> float:
        total = len(self.steps)
        return self.success_count / max(total, 1)

    @property
    def consecutive_failures(self) -> int:
        count = 0
        for s in reversed(self.steps):
            if s.status == StepStatus.FAILED:
                count += 1
            elif s.status == StepStatus.SUCCESS:
                break
        return count

    def add_step(self, step: UnifiedStep) -> None:
        self.steps.append(step)

    def get_recent_steps_for_llm(self, n: int = 5, max_chars: int = 2000) -> str:
        """最近 N 步的 LLM 上下文摘要"""
        recent = self.steps[-n:]
        lines = [s.for_llm() for s in recent]
        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[-max_chars:]
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "description": self.description[:200],
            "status": self.status.value,
            "policy_mode": self.policy.mode.value,
            "step_count": len(self.steps),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 2),
            "total_tokens": self.total_tokens,
            "stop_reason": self.stop_reason,
        }
