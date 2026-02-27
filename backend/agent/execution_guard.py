"""
Execution Guard - 企业级执行守卫
根据 Query 意图 + 任务状态 + 工具类型，决定是否允许执行，避免“纯追问”误触发写盘/运行。
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from .query_classifier import Intent

logger = logging.getLogger(__name__)

GUARD_METRICS_DIR = os.environ.get(
    "QUERY_METRICS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "data"),
)
GUARD_METRICS_FILE = os.path.join(GUARD_METRICS_DIR, "execution_guard_metrics.jsonl")
ENABLE_GUARD_METRICS_LOG = os.environ.get("ENABLE_QUERY_METRICS_LOG", "true").lower() == "true"

# 当 intent 为 INFORMATION 时，以下工具视为“高风险”：禁止执行，要求模型根据历史回答
BLOCKED_TOOLS_FOR_INFORMATION_INTENT = frozenset({
    "write_file", "create_and_run_script", "run_shell", "move_file", "copy_file", "delete_file",
    "file_operations",  # 若以统一工具名暴露
})
# 仅读/查询类工具在 information 意图下可放行（可选，按需放宽）
READ_ONLY_TOOLS = frozenset({
    "read_file", "list_directory", "get_system_info", "terminal",  # terminal 仍可能写，可按需收紧
})


@dataclass
class GuardResult:
    """守卫结果"""
    allowed: bool
    reason: str
    intent: str
    tool_name: str

    def to_log_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "intent": self.intent,
            "tool_name": self.tool_name,
        }


def check(
    intent: Intent,
    tool_name: str,
    session_id: Optional[str] = None,
    task_status: Optional[str] = None,
) -> GuardResult:
    """
    根据意图与工具名决定是否允许执行。
    - INFORMATION + 写/执行类工具 → 不允许
    - EXECUTION / GREETING / UNKNOWN → 允许（由下游安全校验负责）
    """
    tool_lower = (tool_name or "").strip().lower()
    if not tool_lower:
        return GuardResult(
            allowed=True,
            reason="no_tool_name",
            intent=intent.value,
            tool_name=tool_name or "",
        )

    if intent == Intent.INFORMATION:
        if tool_lower in BLOCKED_TOOLS_FOR_INFORMATION_INTENT or any(
            blocked in tool_lower for blocked in ["write", "run_shell", "create_and_run", "delete", "move", "copy"]
        ):
            result = GuardResult(
                allowed=False,
                reason="information_intent_blocked_write_or_exec",
                intent=intent.value,
                tool_name=tool_lower,
            )
            logger.info(
                "execution_guard blocked tool=%s intent=%s reason=%s",
                tool_lower, intent.value, result.reason,
            )
            if ENABLE_GUARD_METRICS_LOG and session_id:
                _append_guard_log(session_id, result)
            return result
        # 仅读类可放行（可选）
        if tool_lower in READ_ONLY_TOOLS:
            result = GuardResult(allowed=True, reason="information_intent_read_only", intent=intent.value, tool_name=tool_lower)
            if ENABLE_GUARD_METRICS_LOG and session_id:
                _append_guard_log(session_id, result)
            return result
        # 其他未列出的工具在 information 下也建议拦截，避免误操作
        result = GuardResult(
            allowed=False,
            reason="information_intent_blocked_unknown_tool",
            intent=intent.value,
            tool_name=tool_lower,
        )
        logger.info("execution_guard blocked tool=%s intent=%s reason=%s", tool_lower, intent.value, result.reason)
        if ENABLE_GUARD_METRICS_LOG and session_id:
            _append_guard_log(session_id, result)
        return result

    result = GuardResult(allowed=True, reason="intent_allows_execution", intent=intent.value, tool_name=tool_lower)
    if ENABLE_GUARD_METRICS_LOG and session_id:
        _append_guard_log(session_id, result)
    return result


def _append_guard_log(session_id: str, result: GuardResult) -> None:
    try:
        os.makedirs(GUARD_METRICS_DIR, exist_ok=True)
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "session_id": session_id,
            **result.to_log_dict(),
        }
        with open(GUARD_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Failed to write execution_guard metrics: %s", e)


def get_guard_fallback_message(tool_name: str) -> str:
    """被拦截时注入给模型的说明，引导其根据历史回答"""
    return (
        f"[系统] 当前用户意图被识别为「仅追问信息」。已阻止执行工具「{tool_name}」。"
        "请根据上述对话历史直接回答用户（如项目/文件位置、完成步骤等），不要再次尝试创建或执行操作。"
    )
