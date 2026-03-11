"""
Action Result Schema — 结构化动作执行结果
替代简单的 ToolResult，提供丰富的观察信息、错误分类、环境变化追踪。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from .error_taxonomy import ClassifiedError, classify_error


class ActionOutcome(Enum):
    """动作执行结果"""
    SUCCESS = "success"
    PARTIAL = "partial"          # 部分成功（如多文件操作部分失败）
    FAILED = "failed"
    SKIPPED = "skipped"          # 被跳过（前置条件不满足）
    TIMEOUT = "timeout"


@dataclass
class EnvironmentChange:
    """单个环境变更记录"""
    change_type: str             # "file_created", "file_modified", "file_deleted", "app_opened", "app_closed", "clipboard_changed"
    target: str                  # 变更目标（路径/app名/URL等）
    before: Optional[str] = None # 变更前状态（简短描述）
    after: Optional[str] = None  # 变更后状态
    verified: bool = False       # 是否经过自动验证

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.change_type, "target": self.target, "verified": self.verified}
        if self.before is not None:
            d["before"] = self.before
        if self.after is not None:
            d["after"] = self.after
        return d


@dataclass
class UIObservation:
    """UI 状态观察快照"""
    focused_app: str = ""
    focused_window: str = ""
    visible_text: str = ""       # OCR 或 AX 获取的可见文本（截断）
    screenshot_path: str = ""
    elements_summary: str = ""   # 简要的 UI 元素描述
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.focused_app:
            d["focused_app"] = self.focused_app
        if self.focused_window:
            d["focused_window"] = self.focused_window
        if self.visible_text:
            d["visible_text"] = self.visible_text[:500]
        if self.screenshot_path:
            d["screenshot_path"] = self.screenshot_path
        if self.elements_summary:
            d["elements_summary"] = self.elements_summary[:300]
        return d

    def for_llm(self) -> str:
        """生成给 LLM 的 UI 状态描述"""
        parts = []
        if self.focused_app:
            parts.append(f"当前应用: {self.focused_app}")
        if self.focused_window:
            parts.append(f"窗口: {self.focused_window}")
        if self.visible_text:
            text = self.visible_text[:300]
            parts.append(f"可见文本: {text}")
        if self.elements_summary:
            parts.append(f"UI元素: {self.elements_summary[:200]}")
        return " | ".join(parts) if parts else ""


@dataclass
class ActionResult:
    """
    结构化的动作执行结果。
    包含：执行结果、环境变更、UI观察、错误分类、置信度。
    """
    # 核心结果
    outcome: ActionOutcome
    data: Any = None
    error: Optional[ClassifiedError] = None

    # 执行元数据
    tool_name: str = ""
    action_type: str = ""
    duration_ms: int = 0
    iteration: int = 0

    # 环境变更
    changes: List[EnvironmentChange] = field(default_factory=list)

    # UI 观察
    ui_observation: Optional[UIObservation] = None

    # 置信度 (0.0~1.0)
    confidence: float = 1.0

    # 验证状态
    verified: bool = False
    verify_note: str = ""

    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def success(self) -> bool:
        return self.outcome in (ActionOutcome.SUCCESS, ActionOutcome.PARTIAL)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "outcome": self.outcome.value,
            "success": self.success,
            "tool_name": self.tool_name,
            "action_type": self.action_type,
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
            "verified": self.verified,
        }
        if self.data is not None:
            d["data"] = self.data if not isinstance(self.data, bytes) else "<binary>"
        if self.error:
            d["error"] = self.error.to_dict()
        if self.changes:
            d["changes"] = [c.to_dict() for c in self.changes]
        if self.ui_observation:
            d["ui_observation"] = self.ui_observation.to_dict()
        if self.verify_note:
            d["verify_note"] = self.verify_note
        return d

    def for_llm(self, max_chars: int = 3000) -> str:
        """生成给 LLM 的结构化结果文本"""
        parts = []

        # 结果状态
        status = "✅ 成功" if self.success else "❌ 失败"
        if self.outcome == ActionOutcome.PARTIAL:
            status = "⚠️ 部分成功"
        parts.append(f"[{self.tool_name}/{self.action_type}] {status}")

        # 数据摘要
        if self.data is not None:
            import json
            if isinstance(self.data, dict):
                text = json.dumps(self.data, ensure_ascii=False, indent=1)
                if len(text) > max_chars - 500:
                    text = text[:max_chars - 500] + f"\n... [截断，共 {len(text)} 字符]"
                parts.append(text)
            elif isinstance(self.data, str):
                if len(self.data) > max_chars - 500:
                    parts.append(self.data[:max_chars - 500] + "...")
                else:
                    parts.append(self.data)
            else:
                parts.append(str(self.data)[:max_chars - 500])

        # 错误信息
        if self.error:
            parts.append(self.error.for_llm())

        # 环境变更
        if self.changes:
            change_strs = [f"  - {c.change_type}: {c.target}" for c in self.changes[:5]]
            parts.append("环境变更:\n" + "\n".join(change_strs))

        # 验证结果
        if self.verify_note:
            parts.append(f"验证: {self.verify_note}")

        # UI 观察
        if self.ui_observation:
            ui_text = self.ui_observation.for_llm()
            if ui_text:
                parts.append(f"UI状态: {ui_text}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars - 50] + "\n... [结果已截断]"
        return result

    @staticmethod
    def from_tool_result(tool_result: Any, tool_name: str = "", action_type: str = "") -> "ActionResult":
        """从旧版 ToolResult 转换"""
        if tool_result.success:
            return ActionResult(
                outcome=ActionOutcome.SUCCESS,
                data=tool_result.data,
                tool_name=tool_name,
                action_type=action_type,
            )
        else:
            error = classify_error(
                error_text=tool_result.error or "Unknown error",
                tool_name=tool_name,
                action_type=action_type,
            )
            return ActionResult(
                outcome=ActionOutcome.FAILED,
                data=tool_result.data,
                error=error,
                tool_name=tool_name,
                action_type=action_type,
            )
