"""
Unified Error Taxonomy (v3)
全局一致的错误抽象，便于自愈路由、日志分析，不增加 token 消耗。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import uuid
import logging

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    NETWORK = "network"
    STATE = "state"
    RUNTIME = "runtime"
    UPGRADE = "upgrade"


class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentError:
    """统一错误数据结构，所有异常可转换为此后再传播"""
    error_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    category: ErrorCategory = ErrorCategory.RUNTIME
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    retryable: bool = False
    user_visible: bool = True
    root_cause: Optional[str] = None
    message: str = ""
    details: Optional[dict] = None

    def __post_init__(self):
        if not self.message and self.root_cause:
            self.message = self.root_cause

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "retryable": self.retryable,
            "user_visible": self.user_visible,
            "root_cause": self.root_cause,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return self.message or self.root_cause or f"{self.category.value}:{self.error_id}"


def to_agent_error(
    exc: BaseException,
    category: Optional[ErrorCategory] = None,
    severity: Optional[ErrorSeverity] = None,
    retryable: bool = False,
    user_visible: bool = True,
) -> AgentError:
    """
    将任意异常转换为 AgentError。
    可根据 exc 类型推断 category/severity，调用方可覆盖。
    """
    msg = str(exc)
    if category is None:
        if isinstance(exc, (ConnectionError, TimeoutError)):
            category = ErrorCategory.NETWORK
        elif "tool" in type(exc).__name__.lower() or "tool" in msg.lower():
            category = ErrorCategory.TOOL
        elif "llm" in type(exc).__name__.lower() or "model" in msg.lower():
            category = ErrorCategory.LLM
        else:
            category = ErrorCategory.RUNTIME
    if severity is None:
        severity = ErrorSeverity.MEDIUM
    return AgentError(
        category=category,
        severity=severity,
        retryable=retryable,
        user_visible=user_visible,
        root_cause=msg,
        message=msg,
        details={"exc_type": type(exc).__name__},
    )
