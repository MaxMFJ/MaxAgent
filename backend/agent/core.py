"""
Agent Core Engine - 最小调度核心
Implements the main agent loop with function calling
Supports both remote (function calling) and local (text parsing) models
自愈、升级、图片等副作用通过 EventBus 解耦
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator

from .execution_log_handler import QueueLogHandler

from .llm_client import LLMClient
from .context_manager import context_manager
from .local_tool_parser import LocalToolParser, is_local_model, LOCAL_MODEL_SYSTEM_PROMPT
from .context_enhancer import get_context_enhancer
from .prompt_loader import get_full_system_prompt
from .event_bus import get_event_bus
from .event_schema import (
    Event,
    PRIORITY_TOOL_FAILED,
    PRIORITY_TOOL_NOT_FOUND,
    PRIORITY_PARSE_FAILED,
    PRIORITY_TRIGGER_UPGRADE,
)
from tools import get_all_tools, ToolRegistry
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


def _should_have_tool_call(user_message: str, model_output: str) -> bool:
    """检测用户消息可能期望工具调用但模型未返回（供 parse_failed 上下文）"""
    tool_indicators = [
        "打开", "关闭", "启动", "运行", "创建", "删除", "移动", "复制",
        "读取", "写入", "执行", "命令", "终端", "系统", "内存", "CPU", "磁盘",
        "复制到剪贴板", "粘贴",
    ]
    failure_indicators = ["无法", "找不到", "抱歉", "不能", "失败", "请告诉我", "需要更多信息", "不清楚"]
    user_wants_tool = any(ind in user_message for ind in tool_indicators)
    model_failed = any(ind in model_output for ind in failure_indicators)
    return user_wants_tool and model_failed


class AgentCore:
    """
    Core agent engine - 最小调度核心
    ReAct 循环：构建消息 → 调用 LLM → 解析 tool_calls → 执行 → 追加结果
    自愈/升级/图片通过 EventBus 解耦
    """

    def __init__(
        self,
        llm_client: LLMClient,
        runtime_adapter=None,
        max_iterations: int = 30,
    ):
        self.llm = llm_client
        self.runtime_adapter = runtime_adapter  # DI: 由 main 注入
        self.max_iterations = max_iterations
        self.registry = ToolRegistry()
        self._register_tools()
        self.context_manager = context_manager
    
    def _register_tools(self):
        """Register all available tools（含动态加载 tools/generated/）"""
        tools = get_all_tools(self.runtime_adapter)
        self.registry.register_many(tools)
        loaded = self.registry.load_generated_tools(self.runtime_adapter)
        logger.info(f"Registered {len(self.registry)} tools (dynamic: {loaded})")
    
    @property
    def tools(self) -> List[BaseTool]:
        """Get all registered tools"""
        return self.registry.list_tools()
    
    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get tool schemas for LLM"""
        return self.registry.get_schemas()
    
    def reset_conversation(self, session_id: str = "default"):
        """Clear conversation history for a session"""
        self.context_manager.clear_session(session_id)
    
    async def run(self, user_message: str, session_id: str = "default") -> str:
        """
        Run the agent with a user message
        Returns the final response
        """
        # 获取会话上下文
        context = self.context_manager.get_or_create(session_id)
        context.add_message("user", user_message)
        
        # 构建消息列表（使用语义搜索优化上下文）
        context_messages = context.get_context_messages(current_query=user_message)
        messages = [
            {"role": "system", "content": get_full_system_prompt()},
            *context_messages
        ]
        
        logger.info(f"Context: {len(context_messages)} messages for query")
        
        tool_schemas = self.get_tool_schemas()
        
        for iteration in range(self.max_iterations):
            logger.info(f"Agent iteration {iteration + 1}, session: {session_id}")
            
            response = await self.llm.chat(
                messages=messages,
                tools=tool_schemas if tool_schemas else None
            )
            
            if response.get("tool_calls"):
                tool_results = await self._execute_tools(response["tool_calls"])
                
                messages.append({
                    "role": "assistant",
                    "content": response.get("content"),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                            }
                        }
                        for tc in response["tool_calls"]
                    ]
                })
                
                for tc, result in zip(response["tool_calls"], tool_results):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result.to_string()
                    })
            else:
                final_response = response.get("content", "")
                context.add_message("assistant", final_response)
                return final_response
        
        return "抱歉，我尝试了多次但未能完成任务。请尝试简化您的请求。"
    
    async def run_stream(
        self,
        user_message: str,
        session_id: str = "default",
        extra_system_prompt: str = "",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Run the agent with streaming response
        Yields chunks with type and content
        Supports both remote (function calling) and local (text parsing) models
        """
        # Token 使用量跟踪
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
        
        # 获取会话上下文
        context = self.context_manager.get_or_create(session_id)
        
        # LLM 增强的上下文理解：处理"继续之前的任务"等模糊查询
        enhanced_message = user_message
        try:
            enhancer = get_context_enhancer()
            enhanced_message = await enhancer.enhance_query(
                user_message, 
                context.recent_messages
            )
            if enhanced_message != user_message:
                logger.info(f"Query enhanced: {user_message[:30]}... -> {enhanced_message[:50]}...")
        except Exception as e:
            logger.warning(f"Context enhancement failed: {e}")

        context.add_message("user", user_message)
        
        # 检查是否是本地模型
        provider = self.llm.config.provider
        model_name = self.llm.config.model or ""
        use_local_mode = is_local_model(provider)
        
        # 检查 base_url 来进一步判断是否是本地模型
        base_url = self.llm.config.base_url or ""
        if "localhost" in base_url or "127.0.0.1" in base_url:
            # 即使 provider 不是 ollama/lmstudio，但 URL 是本地的，也使用本地模式
            if not use_local_mode:
                logger.info(f"Detected local URL ({base_url}), switching to local mode")
                use_local_mode = True
        
        # 构建消息列表（使用增强后的查询进行语义搜索）
        context_messages = context.get_context_messages(current_query=enhanced_message)
        
        base_prompt = LOCAL_MODEL_SYSTEM_PROMPT if use_local_mode else get_full_system_prompt()
        system_prompt = f"{base_prompt}\n\n{extra_system_prompt}" if extra_system_prompt else base_prompt
        
        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages
        ]
        
        logger.info(f"Context: {len(context_messages)} messages for query, local_mode={use_local_mode}, provider={provider}, model={model_name}")
        
        # 本地模型不传递 tools（通过 prompt 描述工具）
        tool_schemas = None if use_local_mode else self.get_tool_schemas()
        accumulated_content = ""
        
        for iteration in range(self.max_iterations):
            logger.info(f"Agent stream iteration {iteration + 1}, session: {session_id}, messages: {len(messages)}, local_mode={use_local_mode}")
            
            tool_calls = []
            current_content = ""
            
            try:
                logger.info(f"Starting LLM stream (local_mode={use_local_mode})...")
                async for chunk in self.llm.chat_stream(
                    messages=messages,
                    tools=tool_schemas
                ):
                    logger.debug(f"Received chunk: {chunk.get('type')}")
                    
                    if chunk["type"] == "content" and chunk.get("content"):
                        current_content += chunk["content"]
                        # 本地模型：暂存内容，稍后解析
                        if not use_local_mode:
                            yield {"type": "content", "content": chunk["content"]}
                    
                    elif chunk["type"] == "tool_call":
                        tool_calls.append(chunk["tool_call"])
                        logger.info(f"Tool call detected: {chunk['tool_call']['name']}")
                        yield {
                            "type": "tool_call",
                            "tool_name": chunk["tool_call"]["name"],
                            "tool_args": chunk["tool_call"]["arguments"]
                        }
                    
                    elif chunk["type"] == "finish":
                        logger.info(f"Stream finished: {chunk.get('finish_reason')}")
                        # 累加 token 使用量
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                            total_usage["total_tokens"] += usage.get("total_tokens", 0)
                            logger.info(f"Accumulated token usage: {total_usage}")
                    
                    elif chunk["type"] == "error":
                        logger.error(f"Stream error: {chunk.get('error')}")
                        yield {"type": "error", "error": chunk["error"]}
                        return
                
                # 本地模型：从文本中解析工具调用
                if use_local_mode and current_content:
                    parsed_tool, remaining_text = LocalToolParser.parse_response(current_content)
                    if parsed_tool:
                        tool_calls.append(parsed_tool)
                        logger.info(f"Local model tool call parsed: {parsed_tool['name']}")
                        yield {
                            "type": "tool_call",
                            "tool_name": parsed_tool["name"],
                            "tool_args": parsed_tool["arguments"]
                        }
                        # 如果有剩余文本，发送
                        if remaining_text:
                            yield {"type": "content", "content": remaining_text}
                            current_content = remaining_text
                        else:
                            current_content = ""
                    else:
                        yield {"type": "content", "content": current_content}
                        if _should_have_tool_call(user_message, current_content):
                            get_event_bus().publish(Event(
                                type="parse_failed",
                                payload={
                                    "session_id": session_id,
                                    "error": f"LocalToolParser failed to parse tool call from: {current_content[:200]}",
                                    "context": {
                                        "user_message": user_message,
                                        "model_output": current_content[:500],
                                        "provider": provider,
                                        "local_model_active": use_local_mode,
                                    },
                                },
                                priority=PRIORITY_PARSE_FAILED,
                            ))
                
                logger.info(f"LLM stream completed. Tool calls: {len(tool_calls)}, Content length: {len(current_content)}")
                
                if tool_calls:
                    yield {"type": "tool_executing", "count": len(tool_calls)}
                    
                    tool_results = []
                    async for ev in self._execute_tools_with_streaming_logs(tool_calls):
                        if ev.get("type") == "execution_log":
                            yield ev
                        else:
                            tool_results = ev.get("results", [])
                    
                    if use_local_mode:
                        # 本地模型：将工具调用和结果作为对话历史
                        # 添加助手的工具调用消息
                        tool_call_desc = f"我需要执行 {tool_calls[0]['name']} 工具"
                        messages.append({
                            "role": "assistant",
                            "content": tool_call_desc
                        })
                        
                        # 将工具结果作为用户消息（模拟系统反馈）
                        for tc, result in zip(tool_calls, tool_results):
                            result_text = LocalToolParser.format_tool_result(tc["name"], result)
                            messages.append({
                                "role": "user",
                                "content": result_text
                            })
                            yield {
                                "type": "tool_result",
                                "tool_name": tc["name"],
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
                                            "tool_name": tc["name"],
                                            "user_message": user_message,
                                        },
                                        priority=PRIORITY_TOOL_NOT_FOUND,
                                    ))
                                elif result.data.get("trigger_upgrade"):
                                    reason = result.data.get("reason", "")
                                    logger.info(f"Tool upgrade triggered by {tc['name']}: {reason[:80]}...")
                                    get_event_bus().publish(Event(
                                        type="trigger_upgrade",
                                        payload={
                                            "session_id": session_id,
                                            "reason": reason,
                                            "tool_name": tc["name"],
                                            "user_message": user_message,
                                        },
                                        priority=PRIORITY_TRIGGER_UPGRADE,
                                    ))
                            if not result.success:
                                get_event_bus().publish(Event(
                                    type="tool_failed",
                                    payload={"tool": tc["name"], "args": tc.get("arguments", {}), "error": result.error},
                                    priority=PRIORITY_TOOL_FAILED,
                                ))
                    else:
                        # 远程模型：使用标准 function calling 格式
                        messages.append({
                            "role": "assistant",
                            "content": current_content if current_content else None,
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False)
                                    }
                                }
                                for tc in tool_calls
                            ]
                        })
                        
                        for tc, result in zip(tool_calls, tool_results):
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result.to_string()
                            })
                            yield {
                                "type": "tool_result",
                                "tool_name": tc["name"],
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
                                            "tool_name": tc["name"],
                                            "user_message": user_message,
                                        },
                                        priority=PRIORITY_TOOL_NOT_FOUND,
                                    ))
                                elif result.data.get("trigger_upgrade"):
                                    reason = result.data.get("reason", "")
                                    logger.info(f"Tool upgrade triggered by {tc['name']}: {reason[:80]}...")
                                    get_event_bus().publish(Event(
                                        type="trigger_upgrade",
                                        payload={
                                            "session_id": session_id,
                                            "reason": reason,
                                            "tool_name": tc["name"],
                                            "user_message": user_message,
                                        },
                                        priority=PRIORITY_TRIGGER_UPGRADE,
                                    ))
                            if not result.success:
                                get_event_bus().publish(Event(
                                    type="tool_failed",
                                    payload={"tool": tc["name"], "args": tc.get("arguments", {}), "error": result.error},
                                    priority=PRIORITY_TOOL_FAILED,
                                ))
                else:
                    # 检查是否收到空响应
                    if not current_content.strip():
                        logger.warning(f"Empty response from LLM in iteration {iteration + 1}")
                        
                        # 如果是第一次空响应，尝试重新提示
                        if iteration == 0:
                            # 添加提示让模型继续
                            messages.append({
                                "role": "user",
                                "content": "请根据我的问题给出回答。"
                            })
                            continue
                        else:
                            # 多次空响应，返回默认消息
                            yield {"type": "content", "content": "抱歉，我暂时无法处理这个请求。请稍后再试或换一种方式提问。"}
                            return
                    
                    accumulated_content += current_content
                    # 保存助手回复到上下文
                    context.add_message("assistant", accumulated_content)
                    # 持久化到磁盘
                    self.context_manager.save_session(session_id)
                    logger.info(f"Conversation saved to context, total messages: {len(context.messages)}")
                    # 返回流结束标记，包含总 token 使用量
                    yield {"type": "stream_end", "usage": total_usage}
                    return
                    
            except Exception as e:
                logger.error(f"Error in iteration {iteration + 1}: {e}", exc_info=True)
                yield {"type": "error", "error": str(e)}
                return
        
        yield {"type": "error", "error": "达到最大迭代次数"}
    
    async def _execute_tools(self, tool_calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """Execute a list of tool calls"""
        results = []
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments", {})
            logger.info(f"Executing tool: {name} with args: {args}")
            result = await self.registry.execute(name, **args)
            results.append(result)
            logger.info(f"Tool {name} result: success={result.success}")
        return results

    async def _execute_tools_with_streaming_logs(
        self, tool_calls: List[Dict[str, Any]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute tools and yield execution_log events during execution"""
        results: List[ToolResult] = []
        tools_logger = logging.getLogger("tools")
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments", {})
            action_id = tc.get("id", "")
            queue: asyncio.Queue = asyncio.Queue()
            handler = QueueLogHandler(queue, ["tools"])
            handler.setFormatter(logging.Formatter("%(message)s"))
            tools_logger.addHandler(handler)
            orig_level = tools_logger.level
            tools_logger.setLevel(logging.DEBUG)
            try:
                task = asyncio.create_task(self.registry.execute(name, **args))
                while True:
                    try:
                        rec = await asyncio.wait_for(queue.get(), timeout=0.1)
                        yield {
                            "type": "execution_log",
                            "tool_name": name,
                            "action_id": action_id,
                            "level": rec["level"],
                            "message": rec["message"],
                        }
                    except asyncio.TimeoutError:
                        if task.done():
                            break
                        await asyncio.sleep(0)
                result = await task
                while not queue.empty():
                    try:
                        rec = queue.get_nowait()
                        yield {
                            "type": "execution_log",
                            "tool_name": name,
                            "action_id": action_id,
                            "level": rec["level"],
                            "message": rec["message"],
                        }
                    except asyncio.QueueEmpty:
                        break
                results.append(result)
            finally:
                tools_logger.removeHandler(handler)
                tools_logger.setLevel(orig_level)
        yield {"type": "_tool_results", "results": results}
