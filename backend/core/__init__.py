"""
MacAgent v3 Core - 底层框架统一抽象
- 统一错误模型、超时策略、任务状态机、并发限流等
- 在现有代码上升级，不单独 v3 分支
"""
from .error_model import (
    AgentError,
    ErrorCategory,
    ErrorSeverity,
    to_agent_error,
)
from .task_state_machine import (
    TaskState,
    TaskStateMachine,
)
from .concurrency_limiter import (
    get_concurrency_limiter,
    ConcurrencyLimiter,
)
from .timeout_policy import (
    TimeoutPolicy,
    get_timeout_policy,
)

__all__ = [
    "AgentError",
    "ErrorCategory",
    "ErrorSeverity",
    "to_agent_error",
    "TaskState",
    "TaskStateMachine",
    "get_concurrency_limiter",
    "ConcurrencyLimiter",
    "TimeoutPolicy",
    "get_timeout_policy",
]
