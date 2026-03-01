"""
LangChain 兼容模式下的 Chat Runner
使用 create_tool_calling_agent + AgentExecutor，产出与 AgentCore.run_stream 相同的 chunk 格式
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.agents import create_tool_calling_agent, AgentExecutor
    _HAS_LC = True
except ImportError:
    _HAS_LC = False
    create_tool_calling_agent = None
    AgentExecutor = None


from .llm_adapter import MacAgentChatModel
from .tool_adapter import mac_tools_to_langchain
from .memory_adapter import context_messages_to_langchain

# 本地 token 计数器
try:
    from agent.token_counter import count_tokens, count_messages_tokens
except ImportError:
    count_tokens = lambda t: 0
    count_messages_tokens = lambda m: 0


def _get_trace_callbacks() -> List[Any]:
    """
    可观测性钩子：返回 LangChain 可用的 callback 列表，便于接入 LangSmith / OpenTelemetry。
    若设置环境变量 LANGCHAIN_TRACING_V2=true 且 LANGCHAIN_API_KEY 已配置，LangChain 会自动上报到 LangSmith。
    此处预留可追加自定义 callback（如 OpenTelemetry），不改变主流程。
    """
    callbacks: List[Any] = []
    try:
        import os
        if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
            # LangChain 会自动使用 LangSmith callback，无需显式构造
            pass
        # 可在此追加: from langchain_community.callbacks import OpenTelemetryCallbackHandler; callbacks.append(...)
    except Exception:
        pass
    return callbacks


class LangChainChatRunner:
    """
    兼容模式下使用 LangChain Agent 执行对话，产出与 AgentCore.run_stream 一致的 chunk 类型，
    便于 ws_handler 无差别处理。
    """

    def __init__(
        self,
        llm_client: Any,
        registry: Any,
        context_manager: Any,
        runtime_adapter: Any = None,
        system_prompt_fn: Optional[Any] = None,
        max_iterations: int = 30,
    ):
        if not _HAS_LC:
            raise RuntimeError(
                "LangChain is required for LangChainChatRunner. "
                "Install with: pip install -r requirements-langchain.txt"
            )
        self.llm_client = llm_client
        self.registry = registry
        self.context_manager = context_manager
        self.runtime_adapter = runtime_adapter
        self.system_prompt_fn = system_prompt_fn or (lambda q: "")
        self.max_iterations = max_iterations
        self._bind_target_fn = None  # 由 session 的 current_task 提供，在 run_stream 内设置

    async def run_stream(
        self,
        user_message: str,
        session_id: str = "default",
        extra_system_prompt: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        与 AgentCore.run_stream 相同的签名与 chunk 类型：
        type: content | tool_call | tool_result | tool_executing | stream_end | error
        """
        context = self.context_manager.get_or_create(session_id)
        context.add_message("user", user_message)

        try:
            from agent.agent_state import get_current_task
            from agent.task_context_manager import bind_target_to_tool_args
            self._bind_target_fn = lambda n, a: bind_target_to_tool_args(n, a, get_current_task(session_id))
        except Exception:
            self._bind_target_fn = None

        system_content = self.system_prompt_fn(user_message)
        if extra_system_prompt:
            system_content = f"{system_content}\n\n{extra_system_prompt}".strip()
        context_messages = context.get_context_messages(current_query=user_message)
        lc_messages = context_messages_to_langchain(context_messages)
        if not lc_messages:
            lc_messages = []

        llm = MacAgentChatModel(llm_client=self.llm_client)
        tools = mac_tools_to_langchain(
            self.registry,
            query=user_message,
            max_tools=8,
            always_include=["terminal", "file_operations", "app_control"],
            bind_target_fn=self._bind_target_fn,
        )
        llm_with_tools = llm.bind_tools(tools)

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_content),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm_with_tools, tools, prompt)
        trace_callbacks = _get_trace_callbacks()
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=self.max_iterations,
            return_intermediate_steps=True,
            handle_parsing_errors=True,
            callbacks=trace_callbacks if trace_callbacks else None,
        )

        input_dict = {
            "input": user_message,
            "chat_history": lc_messages,
        }

        # 本地计算 prompt tokens
        prompt_messages = [{"role": "system", "content": system_content}]
        for m in context_messages:
            prompt_messages.append(m)
        prompt_messages.append({"role": "user", "content": user_message})
        prompt_tokens = count_messages_tokens(prompt_messages)
        completion_content = ""

        try:
            final_output = None
            content_yielded = False
            async for event in executor.astream_events(input_dict, version="v2"):
                kind = event.get("event", "")
                data = event.get("data", {})

                if kind == "on_chat_model_stream":
                    chunk = data.get("chunk") or data.get("output")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        completion_content += chunk.content
                        yield {"type": "content", "content": chunk.content}
                        content_yielded = True

                elif kind == "on_tool_start":
                    name = data.get("name", "")
                    inp = data.get("input", {})
                    if isinstance(inp, str):
                        try:
                            inp = json.loads(inp) if inp else {}
                        except Exception:
                            inp = {}
                    if not isinstance(inp, dict):
                        inp = {}
                    yield {
                        "type": "tool_call",
                        "tool_name": name,
                        "tool_args": inp,
                    }
                    yield {"type": "tool_executing", "count": 1}

                elif kind == "on_tool_end":
                    out = data.get("output", "")
                    name = data.get("name", "")
                    result_str = out[:500] if isinstance(out, str) else str(out)[:500]
                    yield {
                        "type": "tool_result",
                        "tool_name": name,
                        "success": True,
                        "result": result_str,
                        "data": out if isinstance(out, dict) else {"data": out},
                    }

                elif kind == "on_chain_end":
                    output = data.get("output", {})
                    if isinstance(output, dict) and "output" in output:
                        final_output = output["output"]
                    elif isinstance(output, str):
                        final_output = output

            if final_output and not content_yielded:
                completion_content += final_output
                yield {"type": "content", "content": final_output}
            context.add_message("assistant", final_output or "")
            self.context_manager.save_session(session_id)
        except Exception as e:
            logger.exception("LangChainChatRunner run_stream error")
            yield {"type": "error", "error": str(e)}
            return

        # 本地计算 completion tokens
        completion_tokens = count_tokens(completion_content)
        total_tokens = prompt_tokens + completion_tokens
        total_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        logger.info(f"LangChain local token count: {total_usage}")
        yield {"type": "stream_end", "usage": total_usage}
