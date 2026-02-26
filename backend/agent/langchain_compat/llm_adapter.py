"""
将 MacAgent LLMClient 适配为 LangChain BaseChatModel
使现有 LLM 可在 LCEL 链、create_tool_calling_agent 中使用
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import (
        AIMessage,
        BaseMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import BaseTool
    from langchain_core.messages.tool_calls import ToolCall

    _HAS_LC = True
except ImportError:
    _HAS_LC = False
    BaseChatModel = None  # type: ignore
    AIMessage = None
    HumanMessage = None
    SystemMessage = None
    ToolMessage = None
    ToolCall = None


def _messages_to_openai(messages: Sequence[BaseMessage]) -> List[Dict[str, Any]]:
    """LangChain BaseMessage 列表 -> OpenAI 风格 messages"""
    out = []
    for m in messages:
        role = getattr(m, "type", "") or ""
        if role == "system":
            out.append({"role": "system", "content": (m.content or "")})
        elif role == "human":
            out.append({"role": "user", "content": (m.content or "")})
        elif role == "ai":
            content = m.content or ""
            tc = getattr(m, "tool_calls", None) or []
            if tc:
                out.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": t.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": t.get("name", ""),
                                "arguments": json.dumps(t.get("args") or {}, ensure_ascii=False),
                            },
                        }
                        for t in tc
                    ],
                })
            else:
                out.append({"role": "assistant", "content": content})
        elif role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": getattr(m, "tool_call_id", ""),
                "content": (m.content or ""),
            })
        else:
            if hasattr(m, "content") and m.content:
                out.append({"role": "user", "content": str(m.content)})
    return out


def _tool_schemas_from_langchain(tools: Optional[Sequence[BaseTool]]) -> Optional[List[Dict[str, Any]]]:
    """LangChain tools -> OpenAI function schema 列表"""
    if not tools:
        return None
    schemas = []
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "func", {}).__name__
        desc = getattr(t, "description", "") or ""
        args = getattr(t, "args_schema", None)
        if args is not None and hasattr(args, "schema"):
            params = args.schema()
        else:
            params = {"type": "object", "properties": {}, "required": []}
        schemas.append({"name": name, "description": desc, "parameters": params})
    return schemas


class MacAgentChatModel(BaseChatModel if _HAS_LC else object):  # type: ignore
    """
    LangChain BaseChatModel 实现，内部委托 MacAgent LLMClient。
    支持 bind_tools 与 tool_calls 返回，可用于 create_tool_calling_agent。
    """

    llm_client: Any = None  # LLMClient
    tool_schemas: Optional[List[Dict[str, Any]]] = None  # 当前绑定的工具 schema（OpenAI 格式）

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        llm_client: Any,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        if not _HAS_LC:
            raise RuntimeError("langchain-core is required. Install with: pip install -r requirements-langchain.txt")
        super().__init__(**kwargs)
        self.llm_client = llm_client
        self.tool_schemas = tool_schemas

    def bind_tools(self, tools: Sequence[BaseTool]) -> "MacAgentChatModel":
        """绑定 LangChain 工具，返回新实例（LangChain 约定）"""
        schemas = _tool_schemas_from_langchain(tools)
        return MacAgentChatModel(llm_client=self.llm_client, tool_schemas=schemas)

    @property
    def _llm_type(self) -> str:
        return "mac_agent_chat"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """同步生成；兼容层推荐使用异步，此处用 asyncio 转调"""
        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, run_manager=run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """异步生成：调用 MacAgent LLMClient.chat，返回 AIMessage（含 tool_calls）"""
        oai_messages = _messages_to_openai(messages)
        tools = self.tool_schemas
        try:
            response = await self.llm_client.chat(
                messages=oai_messages,
                tools=tools,
                tool_choice="auto" if tools else "none",
            )
        except Exception as e:
            logger.exception("MacAgentChatModel _agenerate error")
            raise

        content = response.get("content") or ""
        tool_calls_raw = response.get("tool_calls") or []
        tool_calls = [
            ToolCall(id=tc.get("id", ""), name=tc.get("name", ""), args=tc.get("arguments") or {})
            for tc in tool_calls_raw
        ]
        msg = AIMessage(content=content, tool_calls=tool_calls)
        gen = ChatGeneration(message=msg)
        return ChatResult(generations=[gen])
