"""
Concurrency Limiter (v3)
防止多 AutonomousAgent / 多 LLM 并发导致崩溃。
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# 与方案一致
MAX_CONCURRENT_AUTONOMOUS = 2
MAX_CONCURRENT_LLM = 4

_default_limiter: Optional["ConcurrencyLimiter"] = None


class ConcurrencyLimiter:
    """全局并发限流：Autonomous 与 LLM 分别用 Semaphore 控制."""

    def __init__(
        self,
        max_autonomous: int = MAX_CONCURRENT_AUTONOMOUS,
        max_llm: int = MAX_CONCURRENT_LLM,
    ):
        self._autonomous_sem = asyncio.Semaphore(max_autonomous)
        self._llm_sem = asyncio.Semaphore(max_llm)
        self._max_autonomous = max_autonomous
        self._max_llm = max_llm

    @asynccontextmanager
    async def autonomous_slot(self):
        """占用一个 Autonomous 执行槽，执行完毕或异常时释放."""
        async with self._autonomous_sem:
            logger.debug("ConcurrencyLimiter: acquired autonomous slot")
            try:
                yield
            finally:
                logger.debug("ConcurrencyLimiter: released autonomous slot")

    @asynccontextmanager
    async def llm_slot(self):
        """占用一个 LLM 调用槽（可选，用于集中限流 LLM 请求）."""
        async with self._llm_sem:
            logger.debug("ConcurrencyLimiter: acquired LLM slot")
            try:
                yield
            finally:
                logger.debug("ConcurrencyLimiter: released LLM slot")

    @property
    def max_autonomous(self) -> int:
        return self._max_autonomous

    @property
    def max_llm(self) -> int:
        return self._max_llm


def get_concurrency_limiter() -> ConcurrencyLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = ConcurrencyLimiter()
    return _default_limiter


def set_concurrency_limiter(limiter: ConcurrencyLimiter) -> None:
    global _default_limiter
    _default_limiter = limiter
