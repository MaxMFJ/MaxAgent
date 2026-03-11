"""
Error Taxonomy — 结构化错误分类体系
将所有 Agent 执行错误归类为可操作的类别，支持自动恢复策略选择。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


class ErrorCategory(Enum):
    """一级错误分类"""
    ENVIRONMENT = "environment"      # 环境问题（文件不存在、权限不足等）
    TOOL = "tool"                    # 工具执行失败
    PARSE = "parse"                  # LLM 输出解析失败
    UI = "ui"                        # UI 交互失败（元素找不到、窗口消失等）
    NETWORK = "network"              # 网络相关错误
    TIMEOUT = "timeout"              # 超时
    PERMISSION = "permission"        # 权限拒绝
    RESOURCE = "resource"            # 资源不足（磁盘满、内存不足等）
    LOGIC = "logic"                  # 逻辑错误（前置条件不满足等）
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"          # 可忽略，不影响主流程
    MEDIUM = "medium"    # 需要重试或换策略
    HIGH = "high"        # 需要升级处理或人工干预
    CRITICAL = "critical"  # 必须停止执行


class RecoveryStrategy(Enum):
    """建议的恢复策略"""
    RETRY = "retry"              # 原样重试
    RETRY_MODIFIED = "retry_modified"  # 修改参数后重试
    SKIP = "skip"                # 跳过当前步骤
    ALTERNATIVE = "alternative"  # 换一种方法
    ESCALATE = "escalate"        # 升级（换模型或人工）
    ABORT = "abort"              # 终止任务
    WAIT = "wait"                # 等待（资源释放/网络恢复）


@dataclass
class ClassifiedError:
    """结构化错误描述"""
    category: ErrorCategory
    severity: ErrorSeverity
    recovery: RecoveryStrategy
    message: str
    original_error: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""
    retryable: bool = True
    max_retries: int = 2
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "recovery": self.recovery.value,
            "message": self.message,
            "original_error": self.original_error,
            "details": self.details,
            "suggested_action": self.suggested_action,
            "retryable": self.retryable,
            "max_retries": self.max_retries,
        }

    def for_llm(self) -> str:
        """生成给 LLM 的错误描述，包含恢复建议"""
        parts = [f"[{self.category.value.upper()}] {self.message}"]
        if self.suggested_action:
            parts.append(f"建议操作: {self.suggested_action}")
        if self.retryable:
            parts.append(f"可重试（最多 {self.max_retries} 次）")
        else:
            parts.append("不可重试，需要换策略")
        return " | ".join(parts)


# ─── 错误分类规则 ────────────────────────────────────────────────

_FILE_NOT_FOUND_KEYWORDS = ["no such file", "not found", "does not exist", "FileNotFoundError"]
_PERMISSION_KEYWORDS = ["permission denied", "access denied", "not permitted", "Operation not permitted"]
_TIMEOUT_KEYWORDS = ["timeout", "timed out", "TimeoutError"]
_NETWORK_KEYWORDS = ["connection refused", "connection reset", "network unreachable", "host not found", "DNS"]
_RESOURCE_KEYWORDS = ["disk full", "no space left", "out of memory", "MemoryError"]
_UI_KEYWORDS = ["element not found", "window not found", "AXError", "cannot find", "no matching element"]
_PARSE_KEYWORDS = ["json", "parse error", "SyntaxError", "JSONDecodeError", "invalid json"]


def classify_error(
    error_text: str,
    tool_name: str = "",
    action_type: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> ClassifiedError:
    """
    根据错误文本和上下文自动分类错误。
    返回结构化的 ClassifiedError，包含分类、严重程度和恢复建议。
    """
    lower = error_text.lower()
    ctx = context or {}

    # 文件/路径不存在
    if any(kw in lower for kw in _FILE_NOT_FOUND_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.ENVIRONMENT,
            severity=ErrorSeverity.MEDIUM,
            recovery=RecoveryStrategy.RETRY_MODIFIED,
            message="目标文件或路径不存在",
            original_error=error_text,
            suggested_action="检查路径拼写，或先用 list_directory 确认文件是否存在",
            retryable=True,
            max_retries=2,
            details={"pattern": "file_not_found", "tool": tool_name},
        )

    # 权限拒绝
    if any(kw in lower for kw in _PERMISSION_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.PERMISSION,
            severity=ErrorSeverity.HIGH,
            recovery=RecoveryStrategy.ALTERNATIVE,
            message="权限不足，操作被拒绝",
            original_error=error_text,
            suggested_action="尝试用 sudo 或更换目标路径",
            retryable=False,
            details={"pattern": "permission_denied", "tool": tool_name},
        )

    # 超时
    if any(kw in lower for kw in _TIMEOUT_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            recovery=RecoveryStrategy.RETRY,
            message="操作超时",
            original_error=error_text,
            suggested_action="重试或增加超时时间",
            retryable=True,
            max_retries=2,
            details={"pattern": "timeout", "tool": tool_name},
        )

    # 网络错误
    if any(kw in lower for kw in _NETWORK_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM,
            recovery=RecoveryStrategy.WAIT,
            message="网络连接失败",
            original_error=error_text,
            suggested_action="检查网络连接，等待后重试",
            retryable=True,
            max_retries=3,
            details={"pattern": "network_error", "tool": tool_name},
        )

    # 资源不足
    if any(kw in lower for kw in _RESOURCE_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.RESOURCE,
            severity=ErrorSeverity.CRITICAL,
            recovery=RecoveryStrategy.ABORT,
            message="系统资源不足",
            original_error=error_text,
            suggested_action="清理磁盘空间或释放内存后重试",
            retryable=False,
            details={"pattern": "resource_exhausted", "tool": tool_name},
        )

    # UI 交互失败
    if any(kw in lower for kw in _UI_KEYWORDS) or tool_name in ("gui_automation", "input_control"):
        if any(kw in lower for kw in _UI_KEYWORDS):
            return ClassifiedError(
                category=ErrorCategory.UI,
                severity=ErrorSeverity.MEDIUM,
                recovery=RecoveryStrategy.RETRY_MODIFIED,
                message="UI 元素定位失败",
                original_error=error_text,
                suggested_action="截图确认当前界面状态，重新定位元素或等待页面加载",
                retryable=True,
                max_retries=3,
                details={"pattern": "ui_element_not_found", "tool": tool_name},
            )

    # JSON 解析失败
    if any(kw in lower for kw in _PARSE_KEYWORDS):
        return ClassifiedError(
            category=ErrorCategory.PARSE,
            severity=ErrorSeverity.LOW,
            recovery=RecoveryStrategy.RETRY,
            message="输出解析失败",
            original_error=error_text,
            suggested_action="重新生成，确保输出格式正确",
            retryable=True,
            max_retries=3,
            details={"pattern": "parse_error", "tool": tool_name},
        )

    # 工具执行失败（通用）
    if tool_name:
        return ClassifiedError(
            category=ErrorCategory.TOOL,
            severity=ErrorSeverity.MEDIUM,
            recovery=RecoveryStrategy.RETRY_MODIFIED,
            message=f"工具 {tool_name} 执行失败",
            original_error=error_text,
            suggested_action="检查参数是否正确，换一种方式尝试",
            retryable=True,
            max_retries=2,
            details={"pattern": "tool_failure", "tool": tool_name},
        )

    # 未知错误
    return ClassifiedError(
        category=ErrorCategory.UNKNOWN,
        severity=ErrorSeverity.MEDIUM,
        recovery=RecoveryStrategy.ALTERNATIVE,
        message="未分类的错误",
        original_error=error_text,
        suggested_action="分析错误信息，尝试不同的方法",
        retryable=True,
        max_retries=1,
        details={"pattern": "unknown", "tool": tool_name},
    )


class ErrorTracker:
    """跟踪错误历史，检测重复模式，提供统计"""

    def __init__(self, window_size: int = 10):
        self._history: List[ClassifiedError] = []
        self._window_size = window_size

    def record(self, error: ClassifiedError) -> None:
        self._history.append(error)
        if len(self._history) > self._window_size * 3:
            self._history = self._history[-self._window_size * 2:]

    @property
    def recent(self) -> List[ClassifiedError]:
        return self._history[-self._window_size:]

    def consecutive_same_category(self) -> int:
        """连续相同类别错误的数量"""
        if not self._history:
            return 0
        last_cat = self._history[-1].category
        count = 0
        for e in reversed(self._history):
            if e.category == last_cat:
                count += 1
            else:
                break
        return count

    def should_escalate(self) -> bool:
        """是否应该升级处理"""
        return self.consecutive_same_category() >= 3

    def get_dominant_category(self) -> Optional[ErrorCategory]:
        """最近错误中出现最多的类别"""
        if not self.recent:
            return None
        from collections import Counter
        counts = Counter(e.category for e in self.recent)
        return counts.most_common(1)[0][0]

    def get_recovery_hint(self) -> str:
        """根据错误历史生成恢复提示"""
        if not self._history:
            return ""
        consecutive = self.consecutive_same_category()
        last = self._history[-1]
        if consecutive >= 3:
            return (
                f"⚠️ 已连续 {consecutive} 次遇到 {last.category.value} 类错误。"
                f"强制要求换策略: {last.suggested_action}"
            )
        if consecutive >= 2:
            return f"注意：连续 {consecutive} 次 {last.category.value} 错误，建议换方法"
        return ""

    def clear(self) -> None:
        self._history.clear()

    def reset(self) -> None:
        self.clear()
