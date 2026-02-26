"""
Agent Runtime v2 - 结构化 Tool Runtime
本地模型专用：parse_tool_call → validate → execute → 反馈 → 最终回复
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from .execution_log_handler import QueueLogHandler
from .llm_client import LLMClient
from .context_manager import context_manager
from .task_context_manager import (
    extract_explicit_target,
    resolve_task,
    bind_target_to_tool_args,
    is_single_step_task,
)
from .agent_state import get_current_task, set_current_task, clear_current_task
from .context_enhancer import get_context_enhancer
from .event_bus import get_event_bus
from .event_schema import (
    Event,
    PRIORITY_TOOL_FAILED,
    PRIORITY_TOOL_NOT_FOUND,
    PRIORITY_PARSE_FAILED,
    PRIORITY_TRIGGER_UPGRADE,
)
from tools import get_all_tools, ToolRegistry
from tools.base import ToolResult
from tools.schema_registry import build_from_base_tools
from tools.validator import validate_tool_call
from tools.router import execute_tool, set_router_registry
from llm.tool_parser_v2 import parse_tool_call

logger = logging.getLogger(__name__)

# 极简本地模型 System Prompt
LOCAL_MODEL_SYSTEM_PROMPT_V2 = """你是 Chow Duck，macOS 智能助手。
如果需要使用工具，输出 JSON：{"tool":"工具名","args":{...}}
否则直接用中文回复。"""


def _format_tool_result(tool_name: str, result: ToolResult) -> str:
    """将 ToolResult 转为系统反馈文本"""
    if result.success:
        return f"[系统反馈: 工具 {tool_name} 执行成功]\n结果:\n{result.to_string()}\n\n请根据以上结果，用中文向用户提供完整的回答。"
    return f"[系统反馈: 工具 {tool_name} 执行失败]\n错误: {result.error}\n\n请向用户解释操作失败的原因，并提供替代建议或解决方案。"


def _should_have_tool_call(user_message: str, model_output: str) -> bool:
    """检测用户可能期望工具调用但模型未返回"""
    tool_indicators = [
        "打开", "关闭", "启动", "运行", "创建", "删除", "移动", "复制",
        "读取", "写入", "执行", "命令", "终端", "系统", "内存", "CPU", "磁盘",
        "复制到剪贴板", "粘贴",
    ]
    failure_indicators = ["无法", "找不到", "抱歉", "不能", "失败", "请告诉我", "需要更多信息", "不清楚"]
    user_wants_tool = any(ind in user_message for ind in tool_indicators)
    model_failed = any(ind in model_output for ind in failure_indicators)
    return user_wants_tool and model_failed


class AgentRuntimeV2:
    """
    本地模型 Agent Runtime v2
    流程：LLM → parse_tool_call → validate → execute → 反馈 → LLM 最终回复
    """

    def __init__(
        self,
        llm_client: LLMClient,
        runtime_adapter=None,
        max_iterations: int = 30,
    ):
        self.llm = llm_client
        self.runtime_adapter = runtime_adapter
        self.max_iterations = max_iterations
        self.registry = ToolRegistry()
        self._register_tools()
        set_router_registry(self.registry)

    def _register_tools(self) -> None:
        tools = get_all_tools(self.runtime_adapter)
        self.registry.register_many(tools)
        loaded = self.registry.load_generated_tools(self.runtime_adapter)
        build_from_base_tools(self.registry.list_tools())
        logger.info(f"Runtime v2: registered {len(self.registry)} tools (dynamic: {loaded})")

    async def run_stream(
        self,
        user_message: str,
        session_id: str = "default",
        extra_system_prompt: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行本地模型 Agent 流式对话
        使用 parse_tool_call / validate / execute 流程
        """
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        context = context_manager.get_or_create(session_id)

        enhanced_message = user_message
        try:
            enhancer = get_context_enhancer()
            enhanced_message = await enhancer.enhance_query(user_message, context.recent_messages)
        except Exception as e:
            logger.warning(f"Context enhancement failed: {e}")

        context.add_message("user", user_message)

        explicit_target = extract_explicit_target(user_message)
        current_task = get_current_task(session_id)
        resolved_task = resolve_task(user_message, explicit_target, current_task)
        set_current_task(session_id, resolved_task)

        context_messages = context.get_context_messages(current_query=enhanced_message)
        system_prompt = LOCAL_MODEL_SYSTEM_PROMPT_V2
        if extra_system_prompt:
            system_prompt = f"{system_prompt}\n\n{extra_system_prompt}"

        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages,
        ]
        accumulated_content = ""

        def bind_target(name: str, args: dict) -> dict:
            return bind_target_to_tool_args(name, args, get_current_task(session_id))

        for iteration in range(self.max_iterations):
            current_content = ""
            try:
                async for chunk in self.llm.chat_stream(messages=messages, tools=None):
                    if chunk["type"] == "content" and chunk.get("content"):
                        current_content += chunk["content"]
                        # 本地模式暂不 yield content，等解析后决定（避免把 JSON 当回复发出）
                    elif chunk["type"] == "finish":
                        if chunk.get("usage"):
                            u = chunk["usage"]
                            total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
                            total_usage["completion_tokens"] += u.get("completion_tokens", 0)
                            total_usage["total_tokens"] += u.get("total_tokens", 0)
                    elif chunk["type"] == "error":
                        yield {"type": "error", "error": chunk["error"]}
                        return

                tool_name, args, remaining_text = parse_tool_call(current_content)

                if tool_name:
                    if remaining_text:
                        yield {"type": "content", "content": remaining_text}
                    valid, err = validate_tool_call(tool_name, args or {})
                    if not valid:
                        feedback = f"[系统反馈: 参数校验失败] {err}\n\n请修正后重试或直接回复用户。"
                        messages.append({"role": "assistant", "content": current_content})
                        messages.append({"role": "user", "content": feedback})
                        accumulated_content += current_content
                        continue

                    yield {
                        "type": "tool_call",
                        "tool_name": tool_name,
                        "tool_args": args or {},
                    }
                    yield {"type": "tool_executing", "count": 1}

                    result = await execute_tool(
                        tool_name,
                        args or {},
                        registry=self.registry,
                        bind_target_fn=bind_target,
                    )

                    result_text = _format_tool_result(tool_name, result)
                    messages.append({"role": "assistant", "content": current_content})
                    messages.append({"role": "user", "content": result_text})

                    yield {
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "success": result.success,
                        "result": result.to_string()[:500],
                        "data": result.data,
                    }

                    if isinstance(result.data, dict):
                        if result.data.get("tool_not_found"):
                            get_event_bus().publish(Event(
                                type="tool_not_found",
                                payload={
                                    "session_id": session_id,
                                    "reason": result.error or "未知工具",
                                    "tool_name": tool_name,
                                    "user_message": user_message,
                                },
                                priority=PRIORITY_TOOL_NOT_FOUND,
                            ))
                        elif result.data.get("trigger_upgrade"):
                            get_event_bus().publish(Event(
                                type="trigger_upgrade",
                                payload={
                                    "session_id": session_id,
                                    "reason": result.data.get("reason", ""),
                                    "tool_name": tool_name,
                                    "user_message": user_message,
                                },
                                priority=PRIORITY_TRIGGER_UPGRADE,
                            ))
                    if not result.success:
                        get_event_bus().publish(Event(
                            type="tool_failed",
                            payload={"tool": tool_name, "args": args, "error": result.error},
                            priority=PRIORITY_TOOL_FAILED,
                        ))

                    task = get_current_task(session_id)
                    if result.success and task and is_single_step_task(task.task_type, tool_name):
                        clear_current_task(session_id)

                    accumulated_content += current_content
                    context.add_message("assistant", accumulated_content)
                    context_manager.save_session(session_id)
                    yield {"type": "stream_end", "usage": total_usage}
                    return
                else:
                    if not current_content.strip():
                        if iteration == 0:
                            messages.append({"role": "user", "content": "请根据我的问题给出回答。"})
                            continue
                        yield {"type": "content", "content": "抱歉，我暂时无法处理这个请求。请稍后再试或换一种方式提问。"}
                        return

                    yield {"type": "content", "content": current_content}
                    accumulated_content += current_content
                    context.add_message("assistant", accumulated_content)
                    context_manager.save_session(session_id)
                    yield {"type": "stream_end", "usage": total_usage}
                    return

            except Exception as e:
                logger.exception(f"Runtime v2 iteration {iteration + 1} error")
                yield {"type": "error", "error": str(e)}
                return

        yield {"type": "error", "error": "达到最大迭代次数"}
