"""
L9 — Runtime Intelligence: Tool Metrics + Adaptive Strategy
============================================================
Per-tool aggregate metrics (success rate, avg latency, failure modes).
Adaptive strategy selection: suggest alternative tools or approaches
when a tool repeatedly fails.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Tool Metrics
# ---------------------------------------------------------------------------

@dataclass
class ToolMetricEntry:
    """Single invocation record for a tool."""
    tool_name: str
    success: bool
    latency_ms: float = 0.0
    error_category: str = ""     # from error_taxonomy
    params_hash: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolAggregateMetrics:
    """Aggregate statistics for one tool."""
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    failure_categories: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    recent_successes: int = 0       # last N window
    recent_failures: int = 0

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_calls, 1)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.total_calls, 1)

    @property
    def recent_success_rate(self) -> float:
        recent_total = self.recent_successes + self.recent_failures
        return self.recent_successes / max(recent_total, 1)

    def top_failure_category(self) -> str:
        if not self.failure_categories:
            return ""
        return max(self.failure_categories, key=self.failure_categories.get)

    def for_llm(self) -> str:
        parts = [
            f"calls={self.total_calls}",
            f"success_rate={self.success_rate:.0%}",
            f"avg_latency={self.avg_latency_ms:.0f}ms",
        ]
        top_fail = self.top_failure_category()
        if top_fail:
            parts.append(f"top_failure={top_fail}")
        return ", ".join(parts)


class ToolMetricsCollector:
    """Collects per-task and lifetime tool invocation metrics."""

    RECENT_WINDOW = 10  # last N calls for recency-weighted stats

    def __init__(self) -> None:
        self._entries: List[ToolMetricEntry] = []
        self._by_tool: Dict[str, ToolAggregateMetrics] = defaultdict(ToolAggregateMetrics)
        self._recent_by_tool: Dict[str, List[bool]] = defaultdict(list)

    def record(self, entry: ToolMetricEntry) -> None:
        self._entries.append(entry)
        agg = self._by_tool[entry.tool_name]
        agg.total_calls += 1
        agg.total_latency_ms += entry.latency_ms
        if entry.success:
            agg.success_count += 1
        else:
            agg.failure_count += 1
            if entry.error_category:
                agg.failure_categories[entry.error_category] += 1

        # Sliding window
        window = self._recent_by_tool[entry.tool_name]
        window.append(entry.success)
        if len(window) > self.RECENT_WINDOW:
            window.pop(0)
        agg.recent_successes = sum(1 for s in window if s)
        agg.recent_failures = sum(1 for s in window if not s)

    def get_metrics(self, tool_name: str) -> ToolAggregateMetrics:
        return self._by_tool[tool_name]

    def get_all_metrics(self) -> Dict[str, ToolAggregateMetrics]:
        return dict(self._by_tool)

    def get_unreliable_tools(self, threshold: float = 0.5) -> List[str]:
        """Tools with recent success rate below threshold (min 3 calls)."""
        unreliable = []
        for name, agg in self._by_tool.items():
            if agg.total_calls >= 3 and agg.recent_success_rate < threshold:
                unreliable.append(name)
        return unreliable

    def get_summary_for_llm(self, max_tools: int = 10) -> str:
        """Compact summary of tool reliability for LLM context injection."""
        if not self._by_tool:
            return ""
        # Sort by total calls descending
        sorted_tools = sorted(
            self._by_tool.items(),
            key=lambda kv: kv[1].total_calls,
            reverse=True,
        )[:max_tools]

        lines = ["【工具执行统计】"]
        for name, agg in sorted_tools:
            status = "✅" if agg.success_rate >= 0.8 else ("⚠️" if agg.success_rate >= 0.5 else "❌")
            lines.append(f"  {status} {name}: {agg.for_llm()}")

        unreliable = self.get_unreliable_tools()
        if unreliable:
            lines.append(f"  ⚠ 低可靠工具: {', '.join(unreliable)}")

        return "\n".join(lines)

    def reset(self) -> None:
        self._entries.clear()
        self._by_tool.clear()
        self._recent_by_tool.clear()


# ---------------------------------------------------------------------------
# Adaptive Strategy
# ---------------------------------------------------------------------------

# Tool alternatives: when tool X fails repeatedly, suggest Y
_TOOL_ALTERNATIVES: Dict[str, List[str]] = {
    "click":           ["keyboard_shortcut", "key_press"],
    "type_text":       ["key_press", "clipboard_paste"],
    "read_file":       ["run_shell"],
    "write_file":      ["run_shell"],
    "run_shell":       ["write_file"],
    "open_app":        ["run_shell"],
    "screenshot":      ["get_focused_element"],
    "scroll":          ["key_press"],
}

# Error-category-based suggestions
_ERROR_STRATEGY_HINTS: Dict[str, str] = {
    "TIMEOUT":     "操作超时，建议缩小操作范围或分步执行",
    "PERMISSION":  "权限不足，尝试使用 run_shell 通过命令行操作或检查权限设置",
    "UI":          "UI 元素未找到，尝试先截图确认当前界面状态，或使用键盘快捷键替代点击",
    "NETWORK":     "网络错误，建议等待后重试或检查网络连接",
    "ENVIRONMENT": "环境状态异常，建议先截图确认界面再继续",
    "TOOL":        "工具执行失败，考虑使用替代工具完成相同操作",
    "RESOURCE":    "资源不可用，确认目标文件/路径是否存在",
}


@dataclass
class StrategyAdvice:
    """Actionable advice for the LLM planner."""
    tool_name: str
    advice_type: str          # "alternative" | "hint" | "avoid"
    message: str
    alternatives: List[str] = field(default_factory=list)
    confidence: float = 0.5


class AdaptiveStrategy:
    """
    Generates strategy advice based on tool metrics and error patterns.
    Injected into LLM context to steer better action selection.
    """

    # If recent success rate < this, start suggesting alternatives
    WARN_THRESHOLD = 0.5
    # If recent success rate < this, advise avoidance
    AVOID_THRESHOLD = 0.2

    def __init__(self, metrics: ToolMetricsCollector) -> None:
        self._metrics = metrics

    def advise(self, intended_tool: str) -> Optional[StrategyAdvice]:
        """Get advice before executing `intended_tool`."""
        agg = self._metrics.get_metrics(intended_tool)
        if agg.total_calls < 2:
            return None  # Not enough data

        rate = agg.recent_success_rate

        if rate >= self.WARN_THRESHOLD:
            return None  # Tool is performing fine

        alternatives = _TOOL_ALTERNATIVES.get(intended_tool, [])
        top_failure = agg.top_failure_category()
        hint = _ERROR_STRATEGY_HINTS.get(top_failure, "")

        if rate < self.AVOID_THRESHOLD:
            msg = f"工具 '{intended_tool}' 最近成功率极低 ({rate:.0%})。"
            if hint:
                msg += f" {hint}。"
            if alternatives:
                msg += f" 建议改用: {', '.join(alternatives)}"
            return StrategyAdvice(
                tool_name=intended_tool,
                advice_type="avoid",
                message=msg,
                alternatives=alternatives,
                confidence=0.9,
            )
        else:
            msg = f"工具 '{intended_tool}' 可靠性偏低 ({rate:.0%})。"
            if hint:
                msg += f" {hint}。"
            return StrategyAdvice(
                tool_name=intended_tool,
                advice_type="alternative",
                message=msg,
                alternatives=alternatives,
                confidence=0.7,
            )

    def get_session_advice(self) -> str:
        """
        Generate a compact advisory block for LLM context.
        Covers all problematic tools in this session.
        """
        unreliable = self._metrics.get_unreliable_tools(threshold=self.WARN_THRESHOLD)
        if not unreliable:
            return ""

        lines = ["【策略建议】"]
        for tool_name in unreliable:
            advice = self.advise(tool_name)
            if advice:
                lines.append(f"  • {advice.message}")
        return "\n".join(lines) if len(lines) > 1 else ""


# ---------------------------------------------------------------------------
# Singleton-style convenience
# ---------------------------------------------------------------------------

class RuntimeIntelligence:
    """Facade combining metrics collection and adaptive strategy."""

    def __init__(self) -> None:
        self.metrics = ToolMetricsCollector()
        self.strategy = AdaptiveStrategy(self.metrics)

    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float = 0.0,
        error_category: str = "",
        params_hash: str = "",
    ) -> Optional[StrategyAdvice]:
        """Record a tool call and return advice if the tool is becoming unreliable."""
        entry = ToolMetricEntry(
            tool_name=tool_name,
            success=success,
            latency_ms=latency_ms,
            error_category=error_category,
            params_hash=params_hash,
        )
        self.metrics.record(entry)
        # Return advice if tool is now problematic
        if not success:
            return self.strategy.advise(tool_name)
        return None

    def get_context_for_llm(self, max_chars: int = 800) -> str:
        """Combined metrics + strategy advice for LLM context injection."""
        parts = []
        metrics_summary = self.metrics.get_summary_for_llm()
        if metrics_summary:
            parts.append(metrics_summary)
        strategy_advice = self.strategy.get_session_advice()
        if strategy_advice:
            parts.append(strategy_advice)
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars - 3] + "..."
        return result

    def pre_action_check(self, tool_name: str) -> Optional[str]:
        """
        Quick check before executing a tool.
        Returns warning string if the tool is unreliable, else None.
        """
        advice = self.strategy.advise(tool_name)
        if advice and advice.advice_type == "avoid":
            return advice.message
        return None

    def reset(self) -> None:
        self.metrics.reset()
