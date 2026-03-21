"""
ACP Streaming Adapter — Phase 5

将 ws_handler 内部消息格式映射到标准 ACP 事件格式。
支持 SSE 和 WebSocket 两种传输方式，语义一致。
"""
import logging
from typing import Any, Dict, Optional

from models.acp_models import (
    ACPEvent,
    ACPEventType,
    Visibility,
    VISIBILITY_FILTER,
)

logger = logging.getLogger(__name__)


class StreamingAdapter:
    """将 ws_handler 的内部消息映射到标准 ACP 事件。"""

    # 内部消息 type → ACP 事件类型
    MAPPING: Dict[str, str] = {
        "thinking": ACPEventType.THINKING,
        "extended_thinking": ACPEventType.THINKING,
        "planning": ACPEventType.PLANNING,
        "plan": ACPEventType.PLANNING,
        "action": ACPEventType.ACTION,
        "tool_call": ACPEventType.ACTION,
        "action_result": ACPEventType.ACTION_RESULT,
        "tool_result": ACPEventType.ACTION_RESULT,
        "progress": ACPEventType.PROGRESS,
        "checkpoint": ACPEventType.CHECKPOINT,
        "hitl_request": ACPEventType.HITL_REQUEST,
        "hitl_resolved": ACPEventType.HITL_RESOLVED,
        "duck_delegated": ACPEventType.DELEGATED,
        "delegated": ACPEventType.DELEGATED,
        "duck_task_complete": ACPEventType.DELEGATION_DONE,
        "delegation_done": ACPEventType.DELEGATION_DONE,
        "done": ACPEventType.DONE,
        "task_complete": ACPEventType.DONE,
        "error": ACPEventType.ERROR,
        "cancelled": ACPEventType.CANCELLED,
        "stopped": ACPEventType.CANCELLED,
        # Chat / chunk 消息视为 thinking (verbose)
        "chunk": ACPEventType.THINKING,
        "llm_request_start": ACPEventType.THINKING,
        "llm_request_end": ACPEventType.THINKING,
    }

    def __init__(self, task_id: str, visibility: Visibility = Visibility.STANDARD):
        self.task_id = task_id
        self.visibility = visibility
        self._seq = 0
        self._event_filter = VISIBILITY_FILTER.get(visibility)

    def adapt(self, raw_msg: Dict[str, Any]) -> Optional[ACPEvent]:
        """
        将内部消息转换为 ACP 事件。
        如果消息不在映射中或被可见性过滤，返回 None。
        """
        msg_type = raw_msg.get("type", "")
        event_type = self.MAPPING.get(msg_type)
        if not event_type:
            # 未知类型，debug 级别才放行
            if self.visibility != Visibility.DEBUG:
                return None
            event_type = f"agent.internal.{msg_type}" if msg_type else "agent.unknown"

        # 可见性过滤
        if self._event_filter is not None and event_type not in self._event_filter:
            return None

        self._seq += 1

        # 构建 payload — 移除内部字段
        payload = {}
        for k, v in raw_msg.items():
            if k not in ("type", "session_id", "message_id"):
                payload[k] = v

        return ACPEvent(
            event=event_type,
            task_id=self.task_id,
            seq=self._seq,
            visibility=self.visibility,
            payload=payload,
        )

    def format_sse(self, event: ACPEvent) -> str:
        """格式化为 SSE 文本块。"""
        data = event.model_dump_json()
        return f"id: {event.id}\nevent: {event.event}\ndata: {data}\n\n"
