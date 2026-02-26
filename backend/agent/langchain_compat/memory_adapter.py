"""
将 MacAgent 的 ConversationContext 适配为 LangChain 可用的记忆接口
兼容模式下可将现有上下文注入 LangChain 链，或从 LangChain 写回上下文
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
    from langchain_core.chat_history import BaseChatMessageHistory

    _HAS_LC = True
except ImportError:
    _HAS_LC = False
    BaseChatMessageHistory = None  # type: ignore


def _dict_to_lc_message(m: Dict[str, Any]) -> Optional[BaseMessage]:
    if not _HAS_LC:
        return None
    role = (m.get("role") or "").lower()
    content = m.get("content") or ""
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


def _lc_to_dict(m: BaseMessage) -> Dict[str, Any]:
    return {"role": getattr(m, "type", "user"), "content": (m.content or "")}


class MacAgentMemoryAdapter(BaseChatMessageHistory if _HAS_LC else object):  # type: ignore
    """
    将 MacAgent ConversationContext 适配为 LangChain BaseChatMessageHistory。
    用于兼容模式下把现有会话历史注入 LangChain agent。
    """

    def __init__(self, context: Any, **kwargs: Any):
        if not _HAS_LC:
            raise RuntimeError("langchain-core is required. Install with: pip install -r requirements-langchain.txt")
        super().__init__(**kwargs)
        self._context = context

    @property
    def messages(self) -> List[BaseMessage]:
        out = []
        for m in (self._context.recent_messages or []):
            if not m.get("content"):
                continue
            msg = _dict_to_lc_message(m)
            if msg:
                out.append(msg)
        return out

    def add_user_message(self, message: str) -> None:
        self._context.add_message("user", message)

    def add_ai_message(self, message: str) -> None:
        self._context.add_message("assistant", message)

    def add_message(self, message: BaseMessage) -> None:
        if isinstance(message, HumanMessage):
            self.add_user_message(message.content or "")
        elif isinstance(message, AIMessage):
            self.add_ai_message(message.content or "")
        else:
            self._context.add_message("assistant", message.content or "")

    def clear(self) -> None:
        self._context.clear()


def context_messages_to_langchain(messages: List[Dict[str, Any]]) -> List[BaseMessage]:
    """MacAgent 上下文消息列表 -> LangChain BaseMessage 列表"""
    if not _HAS_LC:
        return []
    out = []
    for m in messages:
        msg = _dict_to_lc_message(m)
        if msg:
            out.append(msg)
    return out
