"""
Global Timeout Policy (v3 - Phase 2)
集中管理 LLM、Tool、WS、Autonomous 超时，所有 async 调用建议通过此策略包装。
"""
from dataclasses import dataclass
import asyncio
import logging
from typing import Optional, TypeVar, AsyncGenerator, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class TimeoutPolicy:
    """统一超时配置（秒）"""
    llm_timeout: float = 120.0
    tool_timeout: float = 60.0
    autonomous_timeout: float = 1800.0   # 30 min
    ws_idle_timeout: float = 120.0

    def with_llm_timeout(self, coro, timeout: Optional[float] = None) -> asyncio.Task:
        """包装 LLM 调用，超时则取消。返回 asyncio.Task，调用方 await task。"""
        t = timeout if timeout is not None else self.llm_timeout
        return asyncio.wait_for(coro, timeout=t)

    def with_tool_timeout(self, coro, timeout: Optional[float] = None):
        """包装 Tool 调用。"""
        t = timeout if timeout is not None else self.tool_timeout
        return asyncio.wait_for(coro, timeout=t)


_default_policy: Optional[TimeoutPolicy] = None


def get_timeout_policy() -> TimeoutPolicy:
    global _default_policy
    if _default_policy is None:
        _default_policy = TimeoutPolicy()
    return _default_policy


def set_timeout_policy(policy: TimeoutPolicy) -> None:
    global _default_policy
    _default_policy = policy
