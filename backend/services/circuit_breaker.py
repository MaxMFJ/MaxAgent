"""
Circuit Breaker — LLM API 故障熔断器

三状态模型:
  CLOSED   → 正常工作，允许请求通过
  OPEN     → 熔断中，立即拒绝所有请求（快速失败）
  HALF_OPEN→ 试探中，允许单个请求通过以探测恢复

参数:
  failure_threshold  连续失败 N 次后熔断（默认 5）
  recovery_timeout   熔断后等待 N 秒进入半开（默认 60）
  success_threshold  半开状态连续成功 N 次后关闭（默认 2）
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider LLM circuit breaker."""

    def __init__(
        self,
        name: str = "llm",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._total_trips = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info(f"[circuit:{self.name}] OPEN → HALF_OPEN (recovery timeout elapsed)")
        return self._state

    def allow_request(self) -> bool:
        """是否允许请求通过。OPEN 状态快速拒绝。"""
        s = self.state
        if s == CircuitState.CLOSED:
            return True
        if s == CircuitState.HALF_OPEN:
            return True  # 允许探测请求
        return False  # OPEN → 拒绝

    def record_success(self):
        """记录成功调用"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info(f"[circuit:{self.name}] HALF_OPEN → CLOSED (recovered)")
        else:
            self._failure_count = 0

    def record_failure(self):
        """记录失败调用"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下一旦失败，重新熔断
            self._state = CircuitState.OPEN
            self._total_trips += 1
            logger.warning(f"[circuit:{self.name}] HALF_OPEN → OPEN (probe failed)")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._total_trips += 1
            logger.warning(
                f"[circuit:{self.name}] CLOSED → OPEN "
                f"(failures={self._failure_count}, threshold={self.failure_threshold})"
            )

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "total_trips": self._total_trips,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# ─── Global Instance Registry ──────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str = "llm") -> CircuitBreaker:
    """获取或创建指定名称的断路器"""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name=name)
    return _breakers[name]


def get_all_circuit_status() -> list[dict]:
    """获取所有断路器状态"""
    return [cb.get_status() for cb in _breakers.values()]
