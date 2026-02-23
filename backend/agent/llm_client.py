"""
Unified LLM Client for DeepSeek and Ollama
Supports both cloud API and local models with a unified interface
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM client"""
    provider: str = "deepseek"  # "deepseek", "ollama", or "lmstudio"
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY"))
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


class LLMClient:
    """Unified LLM client supporting DeepSeek API and Ollama"""
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client: Optional[AsyncOpenAI] = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the OpenAI-compatible client"""
        import httpx
        
        # 增加超时时间以处理慢速网络
        self._client = AsyncOpenAI(
            api_key=self.config.api_key or "dummy",
            base_url=self.config.base_url,
            timeout=httpx.Timeout(120.0, connect=30.0),  # 120秒总超时，30秒连接超时
        )
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
            response = await self._client.chat.completions.create(**kwargs)
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
            "stream_options": {"include_usage": True},  # 请求在流式响应中包含 token 使用量
        }
        
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
            
            stream = await self._client.chat.completions.create(**kwargs)
            
            tool_calls_buffer = {}
            chunk_count = 0
            usage_info = None
            
            async for chunk in stream:
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
                    logger.info(f"Stream finish_reason: {chunk.choices[0].finish_reason}, processed {chunk_count} chunks")
                    if tool_calls_buffer:
                        logger.info(f"Yielding {len(tool_calls_buffer)} tool calls")
                        for idx in sorted(tool_calls_buffer.keys()):
                            tc = tool_calls_buffer[idx]
                            try:
                                tc["arguments"] = json.loads(tc["arguments"])
                            except json.JSONDecodeError:
                                tc["arguments"] = {}
                            yield {"type": "tool_call", "tool_call": tc}
                    
                    yield {"type": "finish", "finish_reason": chunk.choices[0].finish_reason, "usage": usage_info}
            
            logger.info(f"LLM stream loop ended, total chunks: {chunk_count}")
                    
        except Exception as e:
            logger.error(f"LLM stream error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
    
    async def simple_chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Simple chat without tools"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(messages)
        return response.get("content", "")
