"""
Execution Controller — Step 生命周期管理
Agent Operating Runtime 的核心控制器。

职责：
1. Step 生命周期: PENDING → RUNNING → SUCCESS/FAILED/SKIPPED
2. Retry Policy: 结构化重试（指数退避 + 策略切换）
3. Circuit Breaker: 连续失败熔断
4. Step Scheduler: 动作排序（先 gather 后 act）
5. Idempotent Guard: 防重复执行（与现有 idempotent_service 配合）
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from .error_taxonomy import ClassifiedError, ErrorCategory, RecoveryStrategy, classify_error, ErrorTracker
from .action_confidence import ActionConfidenceModel, get_confidence_model

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Step Lifecycle
# ──────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


@dataclass
class StepRecord:
    """单步执行记录"""
    step_id: int
    action_type: str
    status: StepStatus = StepStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3
    last_error: Optional[ClassifiedError] = None
    recovery_used: Optional[RecoveryStrategy] = None
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: int = 0

    @property
    def can_retry(self) -> bool:
        if self.status != StepStatus.FAILED:
            return False
        if self.attempts >= self.max_attempts:
            return False
        if self.last_error and self.last_error.recovery == RecoveryStrategy.ABORT:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "status": self.status.value,
            "attempts": self.attempts,
            "duration_ms": self.duration_ms,
        }
        if self.last_error:
            d["error_category"] = self.last_error.category.value
            d["recovery"] = self.last_error.recovery.value
        return d


# ──────────────────────────────────────────────
# Circuit Breaker
# ──────────────────────────────────────────────

class CircuitState(str, Enum):
    CLOSED = "closed"      # 正常运行
    OPEN = "open"          # 熔断（拒绝执行）
    HALF_OPEN = "half_open"  # 半开（试探性执行）


class CircuitBreaker:
    """
    连续失败熔断器。
    - CLOSED: 正常运行
    - OPEN: 连续 N 次同类失败后熔断，拒绝相同类型的 action
    - HALF_OPEN: 冷却期后允许一次试探
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ):
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        # 按 action_type 独立跟踪
        self._failure_counts: Dict[str, int] = {}
        self._states: Dict[str, CircuitState] = {}
        self._open_time: Dict[str, float] = {}

    def allow(self, action_type: str) -> bool:
        """是否允许执行该类动作"""
        state = self._states.get(action_type, CircuitState.CLOSED)
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            # 检查冷却期
            elapsed = time.time() - self._open_time.get(action_type, 0)
            if elapsed >= self._cooldown:
                self._states[action_type] = CircuitState.HALF_OPEN
                logger.info("Circuit breaker half-open for %s after %.0fs cooldown", action_type, elapsed)
                return True
            return False
        if state == CircuitState.HALF_OPEN:
            return True  # 允许一次试探
        return True

    def record_success(self, action_type: str) -> None:
        self._failure_counts[action_type] = 0
        self._states[action_type] = CircuitState.CLOSED

    def record_failure(self, action_type: str) -> None:
        count = self._failure_counts.get(action_type, 0) + 1
        self._failure_counts[action_type] = count

        state = self._states.get(action_type, CircuitState.CLOSED)

        if state == CircuitState.HALF_OPEN:
            # 半开态下失败 → 重新熔断
            self._states[action_type] = CircuitState.OPEN
            self._open_time[action_type] = time.time()
            logger.warning("Circuit breaker re-opened for %s (half-open fail)", action_type)
        elif count >= self._threshold:
            self._states[action_type] = CircuitState.OPEN
            self._open_time[action_type] = time.time()
            logger.warning(
                "Circuit breaker OPEN for %s (%d consecutive failures)",
                action_type, count,
            )

    def get_state(self, action_type: str) -> CircuitState:
        return self._states.get(action_type, CircuitState.CLOSED)

    def reset(self) -> None:
        self._failure_counts.clear()
        self._states.clear()
        self._open_time.clear()

    def stats(self) -> Dict[str, Any]:
        return {
            action: {
                "state": self._states.get(action, CircuitState.CLOSED).value,
                "failures": self._failure_counts.get(action, 0),
            }
            for action in set(list(self._failure_counts.keys()) + list(self._states.keys()))
        }


# ──────────────────────────────────────────────
# Retry Policy
# ──────────────────────────────────────────────

class RetryPolicy:
    """结构化重试策略"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def get_delay(self, attempt: int) -> float:
        """指数退避延迟"""
        return min(self.base_delay * (2 ** attempt), self.max_delay)

    def should_retry(self, error: Optional[ClassifiedError], attempt: int) -> bool:
        """判断是否应重试"""
        if attempt >= self.max_retries:
            return False
        if error is None:
            return True
        # 根据恢复策略决定
        if error.recovery in (RecoveryStrategy.ABORT, RecoveryStrategy.ESCALATE):
            return False
        if error.recovery == RecoveryStrategy.SKIP:
            return False
        return True

    def suggest_modification(self, error: Optional[ClassifiedError], action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """建议参数修改（retry_modified 策略）"""
        if error is None:
            return params
        if error.recovery == RecoveryStrategy.RETRY_MODIFIED:
            modified = dict(params)
            # 超时错误 → 增加超时
            if error.category == ErrorCategory.TIMEOUT:
                if "timeout" in modified:
                    modified["timeout"] = modified["timeout"] * 2
            # 权限错误 → 尝试 sudo（仅 run_shell）
            if error.category == ErrorCategory.PERMISSION and action_type == "run_shell":
                cmd = modified.get("command", "")
                if cmd and not cmd.startswith("sudo "):
                    modified["command"] = f"sudo {cmd}"
            return modified
        return params


# ──────────────────────────────────────────────
# Failure Memory
# ──────────────────────────────────────────────

@dataclass
class FailureRecord:
    """失败路径记录"""
    action_type: str
    error_category: str
    error_text: str
    params_hash: str
    timestamp: float = field(default_factory=time.time)


class FailureMemory:
    """
    记录失败路径，避免重复尝试已知失败的操作。
    """

    def __init__(self, max_records: int = 100):
        self._records: List[FailureRecord] = []
        self._max = max_records

    def record(self, action_type: str, params: Dict[str, Any], error: ClassifiedError) -> None:
        import hashlib, json
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
        self._records.append(FailureRecord(
            action_type=action_type,
            error_category=error.category.value,
            error_text=error.original_error[:200],
            params_hash=params_hash,
        ))
        if len(self._records) > self._max:
            self._records = self._records[-self._max:]

    def has_failed_before(self, action_type: str, params: Dict[str, Any]) -> Optional[FailureRecord]:
        """检查类似操作是否之前失败过"""
        import hashlib, json
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
        for rec in reversed(self._records):
            if rec.action_type == action_type and rec.params_hash == params_hash:
                return rec
        return None

    def get_failure_summary(self, n: int = 5) -> str:
        """最近失败摘要（给 LLM）"""
        if not self._records:
            return ""
        recent = self._records[-n:]
        lines = [f"  {r.action_type} [{r.error_category}]: {r.error_text[:60]}" for r in recent]
        return "最近失败:\n" + "\n".join(lines)

    def reset(self) -> None:
        self._records.clear()


# ──────────────────────────────────────────────
# Execution Controller
# ──────────────────────────────────────────────

class ExecutionController:
    """
    Agent 运行时核心控制器。
    管理 step 生命周期、重试策略、熔断、失败记忆。
    """

    def __init__(
        self,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        failure_memory: Optional[FailureMemory] = None,
        confidence_model: Optional[ActionConfidenceModel] = None,
    ):
        self.retry_policy = retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.failure_memory = failure_memory or FailureMemory()
        self.confidence = confidence_model or get_confidence_model()
        self._steps: List[StepRecord] = []
        self._step_counter = 0

    def create_step(self, action_type: str, max_attempts: int = 3) -> StepRecord:
        """创建新的 step"""
        self._step_counter += 1
        step = StepRecord(
            step_id=self._step_counter,
            action_type=action_type,
            max_attempts=max_attempts,
        )
        self._steps.append(step)
        return step

    def can_execute(self, action_type: str, params: Dict[str, Any]) -> tuple:
        """
        检查是否可以执行该 action。
        返回 (allowed: bool, reason: str)
        """
        # 1. Circuit breaker 检查
        if not self.circuit_breaker.allow(action_type):
            return False, f"Circuit breaker OPEN for {action_type}（连续失败过多，需等待冷却）"

        # 2. Failure memory 检查
        prev_fail = self.failure_memory.has_failed_before(action_type, params)
        if prev_fail:
            # 相同参数之前失败过 — 降低置信度但不阻止（LLM 可能修改了上下文）
            logger.debug(
                "Action %s with same params failed before: %s",
                action_type, prev_fail.error_text[:60],
            )

        return True, ""

    def on_step_start(self, step: StepRecord) -> None:
        """step 开始执行"""
        step.status = StepStatus.RUNNING
        step.attempts += 1
        step.start_time = time.time()

    def on_step_success(self, step: StepRecord) -> None:
        """step 执行成功"""
        step.status = StepStatus.SUCCESS
        step.end_time = time.time()
        step.duration_ms = int((step.end_time - step.start_time) * 1000)
        self.circuit_breaker.record_success(step.action_type)
        self.confidence.record_outcome(step.action_type, True)

    def on_step_failure(self, step: StepRecord, error: ClassifiedError) -> StepStatus:
        """
        step 执行失败。
        返回建议的下一步状态：RETRYING / FAILED / SKIPPED
        """
        step.end_time = time.time()
        step.duration_ms = int((step.end_time - step.start_time) * 1000)
        step.last_error = error
        self.circuit_breaker.record_failure(step.action_type)
        self.confidence.record_outcome(step.action_type, False)
        self.failure_memory.record(step.action_type, {}, error)

        # 判断是否重试
        if self.retry_policy.should_retry(error, step.attempts):
            step.status = StepStatus.RETRYING
            step.recovery_used = error.recovery
            return StepStatus.RETRYING

        # 是否跳过
        if error.recovery == RecoveryStrategy.SKIP:
            step.status = StepStatus.SKIPPED
            return StepStatus.SKIPPED

        step.status = StepStatus.FAILED
        return StepStatus.FAILED

    def get_retry_delay(self, step: StepRecord) -> float:
        """获取重试延迟"""
        return self.retry_policy.get_delay(step.attempts - 1)

    def get_stats(self) -> Dict[str, Any]:
        """运行统计"""
        total = len(self._steps)
        success = sum(1 for s in self._steps if s.status == StepStatus.SUCCESS)
        failed = sum(1 for s in self._steps if s.status == StepStatus.FAILED)
        skipped = sum(1 for s in self._steps if s.status == StepStatus.SKIPPED)
        retried = sum(s.attempts - 1 for s in self._steps if s.attempts > 1)
        return {
            "total_steps": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "total_retries": retried,
            "circuit_breaker": self.circuit_breaker.stats(),
        }

    def get_failure_summary_for_llm(self) -> str:
        """生成给 LLM 的失败摘要"""
        return self.failure_memory.get_failure_summary()

    def reset(self) -> None:
        """重置所有状态（新任务开始时调用）"""
        self._steps.clear()
        self._step_counter = 0
        self.circuit_breaker.reset()
        self.failure_memory.reset()
        self.confidence.reset()


# 单例
_controller: Optional[ExecutionController] = None


def get_execution_controller() -> ExecutionController:
    global _controller
    if _controller is None:
        _controller = ExecutionController()
    return _controller
