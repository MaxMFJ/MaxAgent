"""
Unified LLM Client for DeepSeek and Ollama
Supports both cloud API and local models with a unified interface
"""

import asyncio
import os
import json
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field

from openai import AsyncOpenAI

try:
    from core.timeout_policy import get_timeout_policy
except ImportError:
    get_timeout_policy = None

logger = logging.getLogger(__name__)


def _default_api_key() -> Optional[str]:
    """优先从持久化配置读取 API key，其次从环境变量"""
    try:
        from config.llm_config import get_persisted_api_key
        return get_persisted_api_key()
    except Exception:
        return os.getenv("DEEPSEEK_API_KEY")


@dataclass
class LLMConfig:
    """Configuration for LLM client"""
    provider: str = "deepseek"  # "deepseek", "ollama", or "lmstudio"
    api_key: Optional[str] = field(default_factory=_default_api_key)
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-chat"))
    temperature: float = 0.7
    max_tokens: int = 4096

    def __post_init__(self):
        if self.provider == "ollama":
            self.base_url = self.base_url or "http://localhost:11434/v1"
            self.model = self.model or "deepseek-r1:8b"
            self.api_key = self.api_key or "ollama"
        elif self.provider == "lmstudio":
            self.base_url = self.base_url or "http://localhost:1234/v1"
            self.api_key = self.api_key or "lm-studio"
        elif self.provider == "newapi":
            # New API 统一网关，默认 cc1 地址，配置见语雀文档
            self.base_url = self.base_url or "https://cc1.newapi.ai/v1"
            self.api_key = self.api_key or ""
        elif self.provider == "openai":
            self.base_url = self.base_url or "https://api.openai.com/v1"
            self.model = self.model or "gpt-4o"
        elif self.provider == "gemini":
            # 通常需使用 OpenAI 兼容网关或 Google 端点，由用户配置
            self.base_url = self.base_url or ""
            self.model = self.model or ""
        elif self.provider == "anthropic":
            # 通常需使用 OpenAI 兼容网关，由用户配置
            self.base_url = self.base_url or ""
            self.model = self.model or ""


class LLMClient:
    """Unified LLM client supporting DeepSeek API and Ollama"""
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client: Optional[AsyncOpenAI] = None
        self._init_client()
    
    @staticmethod
    def _is_local_base_url(url: str) -> bool:
        if not url:
            return False
        u = (url or "").strip().lower()
        return "localhost" in u or "127.0.0.1" in u

    def _init_client(self):
        """Initialize the OpenAI-compatible client. 本地 base_url 时使用直连(trust_env=False)避免代理导致 502。"""
        import httpx

        api_key = self.config.api_key or "dummy"
        if api_key == "dummy" and self.config.provider not in ("ollama", "lmstudio"):
            logger.warning(
                "LLM API key not configured! Set DEEPSEEK_API_KEY in .env or configure via Mac App settings. "
                "Requests will fail with 401."
            )

        base_url = self.config.base_url or ""
        timeout = httpx.Timeout(120.0, connect=30.0)
        kwargs = dict(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        if self._is_local_base_url(base_url):
            kwargs["http_client"] = httpx.AsyncClient(trust_env=False, timeout=timeout)
        self._client = AsyncOpenAI(**kwargs)
        logger.info(f"LLM client initialized: provider={self.config.provider}, model={self.config.model}")
    
    def update_config(self, config: LLMConfig):
        """Update configuration and reinitialize client"""
        self.config = config
        self._init_client()
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto"
    ) -> Dict[str, Any]:
        """
        Send a chat completion request
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            tool_choice: "auto", "none", or specific tool
            
        Returns:
            Response dict with 'content' and optional 'tool_calls'
        """
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = tool_choice
        
        try:
            create_coro = self._client.chat.completions.create(**kwargs)
            if get_timeout_policy is not None:
                response = await get_timeout_policy().with_llm_timeout(create_coro)
            else:
                response = await create_coro
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": None,
                "finish_reason": response.choices[0].finish_reason
            }
            
            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments)
                    }
                    for tc in message.tool_calls
                ]
            
            return result
            
        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a chat completion response
        
        Yields:
            Chunks with 'type' ('content', 'tool_call', 'done') and data
        """
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        # stream_options 仅 DeepSeek/OpenAI 原生 API 支持；New API 等兼容网关可能不支持，会导致空响应
        if self.config.provider in ("deepseek", "openai"):
            kwargs["stream_options"] = {"include_usage": True}
        
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = tool_choice
        
        try:
            logger.info(f"Starting chat stream with model: {self.config.model}, messages: {len(messages)}")
            # 打印最后几条消息用于调试
            for i, msg in enumerate(messages[-3:]):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100] if msg.get('content') else 'None'
                logger.debug(f"Message {len(messages)-3+i}: role={role}, content={content}...")
            
            create_coro = self._client.chat.completions.create(**kwargs)
            if get_timeout_policy is not None:
                stream = await get_timeout_policy().with_llm_timeout(create_coro)
            else:
                stream = await create_coro
            
            tool_calls_buffer = {}
            chunk_count = 0
            usage_info = None
            # 单次等待下一个 chunk 的超时（秒）。若 LM Studio 报错但不断开连接，流可能挂起，超时后向前端返回错误并停止旋转。
            chunk_timeout = 90

            stream_iter = stream.__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=chunk_timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.error(
                        f"LLM stream timeout (no chunk for {chunk_timeout}s). "
                        f"provider={self.config.provider}, model={self.config.model}. "
                        "可能原因: LM Studio 报错(如 Channel Error)未正确关闭连接，或模型负载过高。"
                    )
                    yield {
                        "type": "error",
                        "error": (
                            "LLM 响应超时。可能原因：\n"
                            "1. LM Studio 报错（如 Channel Error）未正确传递到客户端；\n"
                            "2. 模型未加载或负载过高。请查看 LM Studio 日志并重试。"
                        ),
                    }
                    return

                chunk_count += 1

                # 检查是否有 usage 信息（DeepSeek 会在最后一个 chunk 中返回）
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage_info = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens
                    }
                    logger.info(f"Got usage info: {usage_info}")
                
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if not delta:
                    continue
                
                if delta.content:
                    logger.debug(f"Content chunk: {delta.content[:50] if len(delta.content) > 50 else delta.content}")
                    yield {"type": "content", "content": delta.content}
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": ""
                            }
                        
                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += tc.function.arguments
                
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                    logger.info(f"Stream finish_reason: {finish_reason}, processed {chunk_count} chunks")
                    if tool_calls_buffer:
                        truncated = (finish_reason == "length")
                        if truncated:
                            logger.warning(
                                f"Output truncated (finish_reason=length) with {len(tool_calls_buffer)} pending tool calls. "
                                f"Tool call arguments are likely incomplete."
                            )
                        logger.info(f"Yielding {len(tool_calls_buffer)} tool calls (truncated={truncated})")
                        for idx in sorted(tool_calls_buffer.keys()):
                            tc = tool_calls_buffer[idx]
                            try:
                                tc["arguments"] = json.loads(tc["arguments"])
                                tc["_truncated"] = False
                            except json.JSONDecodeError:
                                logger.warning(f"Tool call '{tc['name']}' has invalid JSON arguments (truncated={truncated})")
                                tc["arguments"] = {}
                                tc["_truncated"] = True
                            yield {"type": "tool_call", "tool_call": tc}
                    
                    yield {"type": "finish", "finish_reason": finish_reason, "usage": usage_info}
            
            if chunk_count == 0:
                logger.warning(
                    f"LLM stream returned 0 chunks (provider={self.config.provider}, "
                    f"base_url={self.config.base_url}, model={self.config.model}). "
                    "可能原因: API 地址需要 /v1 后缀、模型名在服务端未配置、或 Token 无效。"
                )
            logger.info(f"LLM stream loop ended, total chunks: {chunk_count}")
                    
        except Exception as e:
            base = (self.config.base_url or "").strip()
            if not base:
                base = "(未配置)"
            logger.error(
                f"LLM stream error: {e} (provider={self.config.provider}, base_url={base}, model={self.config.model})",
                exc_info=True,
            )
            # 对连接类 / Channel 错误返回友好提示，便于用户在设置中检查 API 与 LM Studio
            err_msg = str(e)
            if "Connection" in type(e).__name__ or "Connection" in err_msg or "ConnectError" in err_msg:
                err_msg = (
                    f"无法连接到 API 服务（{base}）。请检查：\n"
                    "1. 网络是否可用；\n"
                    "2. 设置中「API 地址」是否正确（如 New API 使用 https://cc1.newapi.ai/v1）；\n"
                    "3. 若为自建服务，是否已启动。\n"
                    f"原始错误: {e}"
                )
            elif "Channel" in err_msg or "channel" in err_msg:
                err_msg = (
                    f"LM Studio 返回错误: {e}\n"
                    "请检查：1) LM Studio 是否已加载模型；2) 模型是否支持当前请求（如视觉模型需传图）；3) 查看 LM Studio 控制台详细错误。"
                )
            yield {"type": "error", "error": err_msg}
    
    async def simple_chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Simple chat without tools"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(messages)
        return response.get("content", "")
