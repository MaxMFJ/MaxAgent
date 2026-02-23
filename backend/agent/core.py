"""
Agent Core Engine
Implements the main agent loop with function calling
Supports both remote (function calling) and local (text parsing) models
With integrated self-healing capabilities
"""

import json
import logging
import traceback
import base64
from typing import List, Dict, Any, Optional, AsyncGenerator

from .llm_client import LLMClient
from .context_manager import context_manager, ConversationContext
from .local_tool_parser import (
    LocalToolParser, 
    is_local_model, 
    get_system_prompt_for_provider,
    LOCAL_MODEL_SYSTEM_PROMPT
)
from .context_enhancer import get_context_enhancer
from .web_augmented_thinking import ThinkingAugmenter
from tools import get_all_tools, ToolRegistry
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# Lazy import for self-healing to avoid circular imports
_self_healing_agent = None

def get_self_healing():
    global _self_healing_agent
    if _self_healing_agent is None:
        try:
            from .self_healing import get_self_healing_agent
            _self_healing_agent = get_self_healing_agent()
        except ImportError:
            logger.warning("Self-healing module not available")
    return _self_healing_agent

SYSTEM_PROMPT = """你是一个强大的 macOS 智能助手，名叫 MacAgent，可以帮助用户完成各种电脑操作任务。

你拥有以下能力：
1. 文件操作：读取、创建、删除、移动、复制文件和目录
2. 终端命令：执行 shell 命令（可以批量处理文件）
3. 应用控制：打开、关闭、切换应用程序
4. 系统信息：获取 CPU、内存、磁盘、网络等系统状态
5. 剪贴板：读取和写入剪贴板内容
6. 截图：截取屏幕或应用窗口（使用 screenshot 工具 + app_name 参数自动截取）
7. 鼠标键盘：使用 input_control 工具控制鼠标点击、键盘输入

使用指南：
- 仔细理解用户的需求，用最少的步骤完成任务
- **简洁高效**：完成任务后简短报告结果，不要冗长描述
- **截图任务**：截图完成后立即停止，不要做额外的分析或识别操作。图片会自动显示在聊天窗口中
- **高效处理**：批量文件操作优先使用终端命令
- 执行危险操作前先确认

请用中文回复用户。回复要简洁，避免啰嗦。"""


class AgentCore:
    """
    Core agent engine that orchestrates LLM and tools
    Implements the ReAct-style agent loop
    With integrated self-healing capabilities
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        max_iterations: int = 30,
        enable_self_healing: bool = True,
        enable_web_augmentation: bool = True
    ):
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.registry = ToolRegistry()
        self._register_tools()
        # 使用全局上下文管理器而不是本地历史
        self.context_manager = context_manager
        # 自愈功能
        self.enable_self_healing = enable_self_healing
        self._healing_in_progress = False
        self._last_error = None
        # 联网增强思维
        self.enable_web_augmentation = enable_web_augmentation
        self._thinking_augmenter = ThinkingAugmenter() if enable_web_augmentation else None
    
    def _register_tools(self):
        """Register all available tools（含动态加载 tools/generated/）"""
        tools = get_all_tools()
        self.registry.register_many(tools)
        loaded = self.registry.load_generated_tools()
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
            {"role": "system", "content": SYSTEM_PROMPT},
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
    
    async def run_stream(self, user_message: str, session_id: str = "default") -> AsyncGenerator[Dict[str, Any], None]:
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
        
        # 🌐 联网增强思维：为需要实时信息的查询自动搜索
        web_augment_text = ""
        if self.enable_web_augmentation and self._thinking_augmenter:
            try:
                augmentation = await self._thinking_augmenter.augment(user_message)
                if augmentation and augmentation.get("success"):
                    web_augment_text = self._thinking_augmenter.format_augmentation_for_llm(augmentation)
                    if web_augment_text:
                        logger.info(f"Web augmentation added: {augmentation.get('type')}")
                        yield {
                            "type": "web_augmentation",
                            "augmentation_type": augmentation.get("type"),
                            "query": augmentation.get("query"),
                            "success": True
                        }
            except Exception as e:
                logger.warning(f"Web augmentation failed: {e}")
        
        context.add_message("user", user_message)  # 保存原始消息
        
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
        
        # 根据模型类型选择 system prompt
        system_prompt = LOCAL_MODEL_SYSTEM_PROMPT if use_local_mode else SYSTEM_PROMPT
        
        # 如果有联网增强信息，添加到 system prompt
        if web_augment_text:
            system_prompt = f"{system_prompt}\n\n{web_augment_text}"
        
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
                        # 没有工具调用，发送全部内容
                        yield {"type": "content", "content": current_content}
                        
                        # 检测可能的工具调用失败并触发自愈
                        if self.enable_self_healing and not self._healing_in_progress:
                            # 检测是否是应该有工具调用但没有的情况
                            should_have_tool = self._should_have_tool_call(user_message, current_content)
                            if should_have_tool:
                                self._last_error = f"LocalToolParser failed to parse tool call from: {current_content[:200]}"
                                yield {
                                    "type": "self_healing_triggered",
                                    "reason": "tool_parse_failure",
                                    "message": "检测到工具调用解析失败，正在尝试自愈..."
                                }
                                # 异步触发自愈（不阻塞当前响应）
                                async for heal_update in self._trigger_self_healing(
                                    error_message=self._last_error,
                                    context={
                                        "user_message": user_message,
                                        "model_output": current_content[:500],
                                        "provider": provider,
                                        "local_model_active": use_local_mode
                                    }
                                ):
                                    yield heal_update
                
                logger.info(f"LLM stream completed. Tool calls: {len(tool_calls)}, Content length: {len(current_content)}")
                
                if tool_calls:
                    yield {"type": "tool_executing", "count": len(tool_calls)}
                    
                    tool_results = await self._execute_tools(tool_calls)
                    
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
                                "result": result.to_string()[:500]
                            }
                            # 检测工具不存在，触发自我升级
                            if not result.success and isinstance(result.data, dict) and result.data.get("tool_not_found"):
                                yield {
                                    "type": "tool_upgrade_needed",
                                    "reason": result.error or "未知工具",
                                    "tool_name": tc["name"],
                                    "user_message": user_message
                                }
                            # Check if result contains image data
                            if result.success and result.data:
                                image_chunk = self._extract_image_from_result(result.data)
                                if image_chunk:
                                    yield image_chunk
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
                                "result": result.to_string()[:500]
                            }
                            # 检测工具不存在，触发自我升级
                            if not result.success and isinstance(result.data, dict) and result.data.get("tool_not_found"):
                                yield {
                                    "type": "tool_upgrade_needed",
                                    "reason": result.error or "未知工具",
                                    "tool_name": tc["name"],
                                    "user_message": user_message
                                }
                            # Check if result contains image data
                            if result.success and result.data:
                                logger.info(f"[Remote] Checking tool result for image, keys: {result.data.keys() if isinstance(result.data, dict) else 'not dict'}")
                                image_chunk = self._extract_image_from_result(result.data)
                                if image_chunk:
                                    logger.info(f"[Remote] Yielding image chunk, has_base64={bool(image_chunk.get('base64'))}, len={len(image_chunk.get('base64', ''))}")
                                    yield image_chunk
                                else:
                                    logger.warning(f"[Remote] No image data extracted from tool result")
                            else:
                                logger.info(f"[Remote] Skipping image check: success={result.success}, has_data={bool(result.data)}")
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
            args = tc["arguments"]
            
            logger.info(f"Executing tool: {name} with args: {args}")
            result = await self.registry.execute(name, **args)
            results.append(result)
            logger.info(f"Tool {name} result: success={result.success}")
        
        return results
    
    def _extract_image_from_result(self, data: dict) -> Optional[dict]:
        """Extract image data from tool result and create image chunk"""
        if not isinstance(data, dict):
            logger.debug(f"_extract_image_from_result: data is not dict, type={type(data)}")
            return None
        
        # Check for base64 image data
        if "image_base64" in data:
            base64_data = data["image_base64"]
            logger.info(f"Found image_base64 in tool result, length={len(base64_data)}")
            return {
                "type": "image",
                "base64": base64_data,
                "mime_type": data.get("mime_type", "image/png"),
                "path": data.get("screenshot_path") or data.get("path")
            }
        
        # Check for screenshot path (for screenshot tool)
        if "screenshot_path" in data or "path" in data:
            path = data.get("screenshot_path") or data.get("path", "")
            if path and any(path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                logger.info(f"Found screenshot path in tool result: {path}")
                # Also try to read and encode as base64
                try:
                    with open(path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode("utf-8")
                    logger.info(f"Successfully encoded image to base64, length={len(image_data)}")
                    return {
                        "type": "image",
                        "base64": image_data,
                        "mime_type": "image/png",
                        "path": path
                    }
                except Exception as e:
                    logger.warning(f"Failed to read image file: {e}")
                    return {
                        "type": "image",
                        "path": path
                    }
        
        return None
    
    def _should_have_tool_call(self, user_message: str, model_output: str) -> bool:
        """
        Detect if the user message likely expects a tool call but none was made
        """
        # 用户消息中的工具调用指示词
        tool_indicators = [
            "打开", "关闭", "启动", "运行",  # 应用控制
            "创建", "删除", "移动", "复制", "读取", "写入",  # 文件操作
            "执行", "命令", "终端",  # 终端
            "系统", "内存", "CPU", "磁盘",  # 系统信息
            "复制到剪贴板", "粘贴",  # 剪贴板
        ]
        
        # 检查用户消息是否包含工具指示词
        user_wants_tool = any(indicator in user_message for indicator in tool_indicators)
        
        # 检查模型输出是否是道歉或无法执行的回复
        failure_indicators = [
            "无法", "找不到", "抱歉", "不能", "失败",
            "请告诉我", "需要更多信息", "不清楚"
        ]
        model_failed = any(indicator in model_output for indicator in failure_indicators)
        
        # 如果用户期望工具调用，但模型返回了失败相关的内容
        return user_wants_tool and model_failed
    
    async def _trigger_self_healing(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Trigger self-healing process
        """
        healer = get_self_healing()
        if not healer:
            yield {
                "type": "self_healing_status",
                "status": "unavailable",
                "message": "自愈模块不可用"
            }
            return
        
        self._healing_in_progress = True
        
        try:
            stack_trace = traceback.format_exc() if self._last_error else ""
            
            async for update in healer.heal(
                error_message=error_message,
                stack_trace=stack_trace,
                context={
                    **(context or {}),
                    "auto_confirm": True  # 自动确认非危险操作
                }
            ):
                # 将自愈更新转换为前端可用的格式
                yield {
                    "type": "self_healing_update",
                    **update
                }
        
        except Exception as e:
            logger.error(f"Self-healing failed: {e}")
            yield {
                "type": "self_healing_error",
                "error": str(e)
            }
        
        finally:
            self._healing_in_progress = False
