"""
Agent Core Engine - 最小调度核心
Implements the main agent loop with function calling
Supports both remote (function calling) and local (text parsing) models
自愈、升级、图片等副作用通过 EventBus 解耦
"""

import asyncio
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional, AsyncGenerator

from .execution_log_handler import QueueLogHandler

from .llm_client import LLMClient
from .context_manager import context_manager
from .local_tool_parser import LocalToolParser, is_local_model, LOCAL_MODEL_SYSTEM_PROMPT
from llm.tool_parser_v2 import parse_tool_call as parse_tool_call_v2
from .task_context_manager import (
    extract_explicit_target,
    resolve_task,
    bind_target_to_tool_args,
    is_single_step_task,
)
from .agent_state import get_current_task, set_current_task, clear_current_task
from .terminal_session import set_current_session_id
from .context_enhancer import get_context_enhancer
from .prompt_loader import get_full_system_prompt, get_system_prompt_for_query
from .query_classifier import classify, QueryTier
from .execution_guard import check as guard_check, get_guard_fallback_message
from .event_bus import get_event_bus
from .event_schema import (
    Event,
    PRIORITY_TOOL_FAILED,
    PRIORITY_TOOL_NOT_FOUND,
    PRIORITY_PARSE_FAILED,
    PRIORITY_TRIGGER_UPGRADE,
)
from .evomap_bridge import evomap_enhance_context, evomap_record_success
from tools import get_all_tools, ToolRegistry
from tools.base import BaseTool, ToolResult
from tools.schema_registry import build_from_base_tools
from tools.router import execute_tool, set_router_registry

logger = logging.getLogger(__name__)


def _record_created_files(context, tool_call: Dict[str, Any], result: ToolResult) -> None:
    """将工具执行产生的文件路径记录到 context，供后续追问时 LLM 能告知用户位置"""
    if not result.success or not isinstance(result.data, dict):
        return
    name = tool_call.get("name", "")
    if name == "file_operations":
        action = (tool_call.get("arguments") or {}).get("action")
        if action in ("write", "create"):
            path = result.data.get("path")
            if path:
                context.add_created_file(path)
        elif action in ("move", "copy"):
            dest = result.data.get("to")
            if dest:
                context.add_created_file(dest)
    elif name == "developer_tool":
        project_path = result.data.get("project_path")
        if project_path:
            context.add_created_file(project_path)


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
        set_router_registry(self.registry)
        self.context_manager = context_manager
    
    def _register_tools(self):
        """Register all available tools（含动态加载 tools/generated/）"""
        tools = get_all_tools(self.runtime_adapter)
        self.registry.register_many(tools)
        loaded = self.registry.load_generated_tools(self.runtime_adapter)
        build_from_base_tools(self.registry.list_tools())
        logger.info(f"Registered {len(self.registry)} tools (dynamic: {loaded})")
    
    @property
    def tools(self) -> List[BaseTool]:
        """Get all registered tools"""
        return self.registry.list_tools()
    
    def get_tool_schemas(self, query: str = "") -> List[Dict[str, Any]]:
        """Get tool schemas for LLM, optionally pruned by query relevance"""
        if query:
            return self.registry.get_relevant_schemas(
                query,
                max_tools=10,
                always_include=["terminal", "file_operations", "app_control", "capsule", "web_search", "input_control", "screenshot"],
            )
        return self.registry.get_schemas()
    
    def reset_conversation(self, session_id: str = "default"):
        """Clear conversation history for a session"""
        self.context_manager.clear_session(session_id)
        clear_current_task(session_id)
    
    async def run(self, user_message: str, session_id: str = "default") -> str:
        """
        Run the agent with a user message
        Returns the final response
        """
        # 获取会话上下文
        context = self.context_manager.get_or_create(session_id)
        context.add_message("user", user_message)

        # Task Context: 提取显式目标并解析任务
        explicit_target = extract_explicit_target(user_message)
        current_task = get_current_task(session_id)
        resolved_task = resolve_task(user_message, explicit_target, current_task)
        set_current_task(session_id, resolved_task)

        # 构建消息列表（使用语义搜索优化上下文）
        context_messages = context.get_context_messages(current_query=user_message)
        messages = [
            {"role": "system", "content": get_system_prompt_for_query(user_message, session_id)},
            *context_messages
        ]
        
        logger.info(f"Context: {len(context_messages)} messages for query")
        
        tool_schemas = self.get_tool_schemas(query=user_message)
        
        for iteration in range(self.max_iterations):
            logger.info(f"Agent iteration {iteration + 1}, session: {session_id}")
            
            response = await self.llm.chat(
                messages=messages,
                tools=tool_schemas if tool_schemas else None
            )
            
            if response.get("tool_calls"):
                tool_results = await self._execute_tools(response["tool_calls"], session_id)
                
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

        # Task Context: 提取显式目标并解析任务，防止跨任务上下文污染
        explicit_target = extract_explicit_target(user_message)
        current_task = get_current_task(session_id)
        resolved_task = resolve_task(user_message, explicit_target, current_task)
        set_current_task(session_id, resolved_task)
        if explicit_target:
            logger.info(f"TaskContext: explicit target '{explicit_target}' -> new task")

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
        
        # EvoMap: 查询进化网络获取策略增强上下文
        evomap_context = ""
        try:
            evomap_context = await evomap_enhance_context(enhanced_message)
        except Exception as e:
            logger.debug(f"EvoMap context enhancement skipped: {e}")

        # 构建消息列表（使用增强后的查询进行语义搜索）
        context_messages = context.get_context_messages(current_query=enhanced_message)
        
        # 企业级：Query 分级 + 分层 Prompt（intent 注入）
        intent_result = classify(enhanced_message, session_id=session_id)
        base_prompt = LOCAL_MODEL_SYSTEM_PROMPT if use_local_mode else get_system_prompt_for_query(enhanced_message, session_id)
        combined_extra = "\n\n".join(p for p in [extra_system_prompt, evomap_context] if p)
        system_prompt = f"{base_prompt}\n\n{combined_extra}" if combined_extra else base_prompt
        
        messages = [
            {"role": "system", "content": system_prompt},
            *context_messages
        ]
        
        logger.info(f"Context: {len(context_messages)} messages for query, local_mode={use_local_mode}, provider={provider}, model={model_name}")
        
        # 按任务类型动态 max_tokens：简单对话 4096，复杂生成 16384，减少截断
        stream_max_tokens = 4096 if intent_result.tier == QueryTier.SIMPLE else 16384
        logger.info(f"Query tier={intent_result.tier.value} -> max_tokens={stream_max_tokens}")
        
        # 本地模型不传递 tools（通过 prompt 描述工具）
        tool_schemas = None if use_local_mode else self.get_tool_schemas(query=enhanced_message)
        accumulated_content = ""
        
        truncation_retries = 0
        MAX_TRUNCATION_RETRIES = 2

        # 在线模型连续请求间隔（秒），避免网关「没有可用token」/ upstream error。可通过环境变量覆盖。
        _delay = float(os.environ.get("LLM_REQUEST_DELAY_SECONDS", "2.0"))
        if _delay < 0:
            _delay = 0

        for iteration in range(self.max_iterations):
            logger.info(f"Agent stream iteration {iteration + 1}, session: {session_id}, messages: {len(messages)}, local_mode={use_local_mode}")
            
            # 在线模型/网关常对同一 token 限制并发，必须等上一轮流式完全结束后再发下一轮，否则易 500。
            # 非首轮请求前等待，确保网关释放 token 后再发下一请求。
            if iteration > 0 and not use_local_mode and _delay > 0:
                await asyncio.sleep(_delay)
            
            tool_calls = []
            current_content = ""
            finish_reason = None
            llm_start = time.time()
            provider = self.llm.config.provider
            model = self.llm.config.model or ""

            # 供监控中心 exec 展示在线 LLM 请求
            yield {
                "type": "llm_request_start",
                "provider": provider,
                "model": model,
                "iteration": iteration,
            }

            try:
                logger.info(f"Starting LLM stream (local_mode={use_local_mode})...")
                async for chunk in self.llm.chat_stream(
                    messages=messages,
                    tools=tool_schemas,
                    max_tokens=stream_max_tokens,
                ):
                    logger.debug(f"Received chunk: {chunk.get('type')}")
                    
                    if chunk["type"] == "content" and chunk.get("content"):
                        current_content += chunk["content"]
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
                        finish_reason = chunk.get("finish_reason")
                        logger.info(f"Stream finished: {finish_reason}")
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                            total_usage["total_tokens"] += usage.get("total_tokens", 0)
                            logger.info(f"Accumulated token usage: {total_usage}")
                        # 供监控中心 exec 展示在线 LLM 返回
                        latency_ms = int((time.time() - llm_start) * 1000)
                        yield {
                            "type": "llm_request_end",
                            "provider": provider,
                            "model": model,
                            "iteration": iteration,
                            "latency_ms": latency_ms,
                            "usage": {
                                "prompt_tokens": total_usage["prompt_tokens"],
                                "completion_tokens": total_usage["completion_tokens"],
                                "total_tokens": total_usage["total_tokens"],
                            },
                            "response_preview": (current_content[:200] + "…") if len(current_content) > 200 else current_content,
                        }
                    
                    elif chunk["type"] == "error":
                        logger.error(f"Stream error: {chunk.get('error')}")
                        err_msg = chunk.get("error", "unknown")
                        latency_ms = int((time.time() - llm_start) * 1000)
                        yield {
                            "type": "llm_request_end",
                            "provider": provider,
                            "model": model,
                            "iteration": iteration,
                            "latency_ms": latency_ms,
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                            "response_preview": None,
                            "error": str(err_msg)[:200],
                        }
                        yield {"type": "error", "error": err_msg}
                        return
                
                # ── 截断自动续传：finish_reason=length 且 tool call 参数不完整 ──
                if finish_reason == "length" and tool_calls and not use_local_mode:
                    has_truncated = any(tc.get("_truncated") for tc in tool_calls)
                    if has_truncated and truncation_retries < MAX_TRUNCATION_RETRIES:
                        truncation_retries += 1
                        latency_ms = int((time.time() - llm_start) * 1000)
                        yield {
                            "type": "llm_request_end",
                            "provider": provider,
                            "model": model,
                            "iteration": iteration,
                            "latency_ms": latency_ms,
                            "usage": dict(total_usage),
                            "response_preview": (current_content[:200] + "…") if len(current_content) > 200 else current_content,
                            "error": "truncated",
                        }
                        tool_names = ", ".join(tc["name"] for tc in tool_calls)
                        logger.warning(
                            f"Tool call truncated (retry {truncation_retries}/{MAX_TRUNCATION_RETRIES}), "
                            f"tools: [{tool_names}]. Asking LLM to regenerate with shorter output."
                        )
                        yield {
                            "type": "content",
                            "content": f"\n\n⚠️ 生成内容过长被截断，正在重新生成（第 {truncation_retries} 次）...\n\n",
                        }
                        messages.append({
                            "role": "assistant",
                            "content": current_content or f"我需要调用 {tool_names} 工具，但输出被截断了。",
                        })
                        messages.append({
                            "role": "user",
                            "content": (
                                "你的上一次回复因为太长被截断了，工具调用参数不完整。"
                                "请用更简洁的方式重新生成。具体建议：\n"
                                "1. 如果是生成代码/脚本，请将内容拆分为多个步骤，先完成核心部分\n"
                                "2. 减少注释和装饰性内容\n"
                                "3. 如果是生成报告，先生成简要版本"
                            ),
                        })
                        tool_calls = []
                        continue
                
                # 本地模型：使用 Tool Parser v2 解析
                if use_local_mode and current_content:
                    tool_name, args, remaining_text = parse_tool_call_v2(current_content)
                    if tool_name:
                        parsed_tool = {
                            "id": f"local_{tool_name}_{hash(current_content) % 10000}",
                            "name": tool_name,
                            "arguments": args or {},
                        }
                        tool_calls.append(parsed_tool)
                        logger.info(f"Local model tool call parsed (v2): {tool_name}")
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
                
                # 清理内部标记
                for tc in tool_calls:
                    tc.pop("_truncated", None)

                logger.info(f"LLM stream completed. Tool calls: {len(tool_calls)}, Content length: {len(current_content)}")
                
                if tool_calls:
                    # 企业级 Execution Guard：按 intent 拦截信息追问下的写/执行类工具
                    allowed_indices = [i for i, tc in enumerate(tool_calls) if guard_check(intent_result.intent, tc.get("name") or "", session_id).allowed]
                    blocked_indices = [i for i in range(len(tool_calls)) if i not in allowed_indices]
                    allowed_tool_calls = [tool_calls[i] for i in allowed_indices]
                    tool_results = [None] * len(tool_calls)

                    yield {"type": "tool_executing", "count": len(tool_calls)}
                    
                    if allowed_tool_calls:
                        async for ev in self._execute_tools_with_streaming_logs(allowed_tool_calls, session_id):
                            if ev.get("type") == "execution_log":
                                yield ev
                            else:
                                real_results = ev.get("results", [])
                        for idx, real_idx in enumerate(allowed_indices):
                            tool_results[real_idx] = real_results[idx]
                    for i in blocked_indices:
                        tc = tool_calls[i]
                        tool_results[i] = ToolResult(success=False, error=get_guard_fallback_message(tc.get("name") or ""))
                        logger.info("execution_guard blocked tool=%s intent=%s", tc.get("name"), intent_result.intent.value)
                    
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
                            _record_created_files(context, tc, result)
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
                            _record_created_files(context, tc, result)
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
    
    async def _execute_tools(
        self, tool_calls: List[Dict[str, Any]], session_id: str = "default"
    ) -> List[ToolResult]:
        """Execute a list of tool calls (Tool Runtime v2: validate → router)"""
        results = []
        bind_fn = lambda n, a: bind_target_to_tool_args(n, a, get_current_task(session_id))
        for tc in tool_calls:
            name = tc["name"]
            args = dict(tc.get("arguments", {}))
            logger.info(f"Executing tool: {name} with args: {args}")
            set_current_session_id(session_id)
            try:
                result = await execute_tool(name, args, registry=self.registry, bind_target_fn=bind_fn)
            finally:
                set_current_session_id(None)
            results.append(result)
            logger.info(f"Tool {name} result: success={result.success}")
            if result.success:
                task = get_current_task(session_id)
                if task and is_single_step_task(task.task_type, name):
                    clear_current_task(session_id)
        return results

    async def _execute_tools_with_streaming_logs(
        self, tool_calls: List[Dict[str, Any]], session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute tools and yield execution_log events during execution"""
        results: List[ToolResult] = []
        tools_logger = logging.getLogger("tools")
        bind_fn = lambda n, a: bind_target_to_tool_args(n, a, get_current_task(session_id))
        for tc in tool_calls:
            name = tc["name"]
            args = dict(tc.get("arguments", {}))
            action_id = tc.get("id", "")
            queue: asyncio.Queue = asyncio.Queue()
            handler = QueueLogHandler(queue, ["tools"])
            handler.setFormatter(logging.Formatter("%(message)s"))
            tools_logger.addHandler(handler)
            orig_level = tools_logger.level
            tools_logger.setLevel(logging.DEBUG)
            set_current_session_id(session_id)
            try:
                task = asyncio.create_task(
                    execute_tool(name, args, registry=self.registry, bind_target_fn=bind_fn)
                )
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
                # Task Context: 单步任务完成后清除 current_task
                if result.success:
                    task = get_current_task(session_id)
                    if task and is_single_step_task(task.task_type, name):
                        clear_current_task(session_id)
                        logger.info(f"TaskContext: single-step task done, cleared current_task")
            finally:
                set_current_session_id(None)
                tools_logger.removeHandler(handler)
                tools_logger.setLevel(orig_level)
        yield {"type": "_tool_results", "results": results}
