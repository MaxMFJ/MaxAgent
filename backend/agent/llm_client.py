"""
Unified LLM Client for DeepSeek and Ollama
Supports both cloud API and local models with a unified interface
"""

import asyncio
import os
import json
import logging
import random
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field

from openai import AsyncOpenAI

try:
    from core.timeout_policy import get_timeout_policy
except ImportError:
    get_timeout_policy = None

from .llm_utils import extract_text_from_content
from .usage_tracker import UsageTracker
from .token_counter import count_tokens, count_messages_tokens, StreamTokenCounter

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
        elif self.provider == "custom":
            # 旧格式：单一自定义提供商，key/base_url/model 全由用户手动填写
            pass
        elif self.provider.startswith("custom."):
            # 新格式：custom.<id>，从 llm_config.custom_providers 列表中查找配置
            provider_id = self.provider[len("custom."):]
            try:
                from config.llm_config import get_custom_provider_by_id
                slot = get_custom_provider_by_id(provider_id)
                if slot:
                    self.api_key = slag if (slag := (slot.get("api_key") or "").strip()) else self.api_key
                    self.base_url = slot.get("base_url") or self.base_url
                    self.model = slot.get("model") or self.model
            except Exception as _e:
                logger.warning(f"Failed to load custom provider '{provider_id}': {_e}")


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

    # 各模型的最大输出 tokens 上限，超过会导致 API 400 错误
    _MODEL_OUTPUT_LIMITS: dict = {
        "deepseek-chat": 8192,
        "deepseek-reasoner": 8000,
        "deepseek-coder": 8192,
        "gpt-4o-mini": 16384,
        "gpt-3.5-turbo": 4096,
    }

    def _clamp_max_tokens(self, max_tokens: int) -> int:
        """按模型实际输出上限收窄 max_tokens，避免超限导致 400 错误。"""
        model = (self.config.model or "").lower()
        for key, limit in self._MODEL_OUTPUT_LIMITS.items():
            if key in model:
                if max_tokens > limit:
                    logger.debug(f"Clamping max_tokens {max_tokens} → {limit} for model '{model}'")
                    return limit
                return max_tokens
        return max_tokens

    # ─── 指数退避重试 ───────────────────────────────

    _RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}
    _NON_RETRYABLE_KEYWORDS = {"unauthorized", "invalid api key", "quota", "insufficient", "context_length", "token_limit"}

    async def _call_with_retry(self, coro_factory, max_retries: int = 3):
        """带指数退避的 API 调用重试。coro_factory 是一个返回 awaitable 的无参可调用对象。"""
        # Circuit breaker check
        from services.circuit_breaker import get_circuit_breaker
        cb = get_circuit_breaker(self.config.provider or "llm")
        if not cb.allow_request():
            raise RuntimeError(
                f"LLM 断路器已熔断（provider={self.config.provider}）。"
                f"连续失败过多，请等待 {cb.recovery_timeout:.0f}s 后自动恢复，或检查 API 服务状态。"
            )
        # Pre-call rate limit check
        rate_err = UsageTracker.shared().check_rate_limit()
        if rate_err:
            raise RuntimeError(rate_err)
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                coro = coro_factory()
                if get_timeout_policy is not None:
                    result = await get_timeout_policy().with_llm_timeout(coro)
                else:
                    result = await coro
                cb.record_success()
                return result
            except Exception as e:
                last_exc = e
                error_str = str(e).lower()
                # 不可重试的错误立即抛出（不计入断路器）
                if any(kw in error_str for kw in self._NON_RETRYABLE_KEYWORDS):
                    raise
                if "401" in error_str or "403" in error_str or "400" in error_str:
                    raise
                # 记录失败到断路器
                cb.record_failure()
                # 最后一次尝试，不再重试
                if attempt >= max_retries:
                    raise
                # 指数退避 + 抖动
                base_delay = min(2 ** attempt, 8)
                delay = base_delay + random.uniform(0, base_delay * 0.5)
                logger.warning(
                    f"[llm_retry] Attempt {attempt + 1}/{max_retries + 1} failed: {str(e)[:120]}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
        raise last_exc  # unreachable but satisfies type checker

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        max_tokens: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat completion request

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            tool_choice: "auto", "none", or specific tool
            max_tokens: Optional override for output length（避免长报告等场景被截断）
            extra_body: Phase C · 透传给底层 API 的额外请求体字段，例如
                        Anthropic Extended Thinking:
                          {"thinking": {"type": "enabled", "budget_tokens": 8000}}

        Returns:
            Response dict with 'content' and optional 'tool_calls'
        """
        _mt = max_tokens if max_tokens is not None else self.config.max_tokens
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self._clamp_max_tokens(_mt),
        }
        
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = tool_choice

        # Phase C：透传 extra_body（例如 Anthropic Extended Thinking 参数）
        if extra_body:
            kwargs["extra_body"] = extra_body

        try:
            response = await self._call_with_retry(
                lambda: self._client.chat.completions.create(**kwargs)
            )
            message = response.choices[0].message
            content = extract_text_from_content(message.content)
            
            result = {
                "content": content,
                "tool_calls": None,
                "finish_reason": response.choices[0].finish_reason
            }
            if hasattr(response, "usage") and response.usage:
                result["usage"] = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(response.usage, "completion_tokens", 0) or 0,
                    "total_tokens": getattr(response.usage, "total_tokens", 0) or 0,
                }
            
            # 本地 token 计算回退：若 API 未返回 usage 或值全为 0，使用本地计算
            api_usage = result.get("usage")
            if not api_usage or api_usage.get("total_tokens", 0) == 0:
                local_prompt = count_messages_tokens(messages)
                local_completion = count_tokens(content or "")
                result["usage"] = {
                    "prompt_tokens": local_prompt,
                    "completion_tokens": local_completion,
                    "total_tokens": local_prompt + local_completion,
                }
                logger.info(f"Using local token count for chat: {result['usage']}")
            
            if message.tool_calls:
                result["tool_calls"] = []
                for tc in message.tool_calls:
                    # Handle arguments that might already be a dict or might be a JSON string
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            # If parsing fails, keep as string or handle appropriately
                            pass
                    elif not isinstance(args, dict):
                        # If it's neither a string nor a dict, convert to dict if possible
                        try:
                            args = dict(args)
                        except Exception:
                            pass  # Keep original if conversion fails
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args
                    })
            
            # ── Track usage ──
            usage = result.get("usage", {})
            UsageTracker.shared().record_call(
                model=self.config.model,
                provider=self.config.provider,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                success=True,
            )
            
            return result
            
        except Exception as e:
            UsageTracker.shared().record_call(
                model=self.config.model,
                provider=self.config.provider,
                success=False,
                error=str(e)[:200],
            )
            
            # 提供更友好的错误信息
            error_str = str(e).lower()
            if "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str:
                friendly_error = (
                    f"API 认证失败 (401): 请检查 API Key 配置。\n"
                    f"• 如使用 DeepSeek: 设置环境变量 DEEPSEEK_API_KEY 或在 Mac App 设置中配置\n"
                    f"• 如使用 OpenAI: 设置环境变量 OPENAI_API_KEY\n"
                    f"• 如使用 New API: 检查 API Key 和 Base URL 是否正确\n"
                    f"原始错误: {str(e)[:100]}"
                )
                logger.error(friendly_error)
                raise RuntimeError(friendly_error) from e
            elif "429" in error_str or "rate limit" in error_str:
                friendly_error = (
                    f"API 请求频率超限 (429): 请稍后重试或升级 API 配额。\n"
                    f"原始错误: {str(e)[:100]}"
                )
                logger.error(friendly_error)
                raise RuntimeError(friendly_error) from e
            elif "quota" in error_str or "insufficient" in error_str:
                friendly_error = (
                    f"API 配额不足: 请检查账户余额或升级套餐。\n"
                    f"原始错误: {str(e)[:100]}"
                )
                logger.error(friendly_error)
                raise RuntimeError(friendly_error) from e
            
            logger.error(f"LLM chat error: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a chat completion response

        Args:
            max_tokens: Optional override for output length (按任务类型动态传入，简单 4096 / 复杂 16384)
        Yields:
            Chunks with 'type' ('content', 'tool_call', 'done') and data
        """
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self._clamp_max_tokens(max_tokens if max_tokens is not None else self.config.max_tokens),
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
            
            # 本地计算 prompt tokens（用于 API 不返回 usage 的情况）
            local_prompt_tokens = count_messages_tokens(messages)
            token_counter = StreamTokenCounter(prompt_tokens=local_prompt_tokens)
            
            stream = await self._call_with_retry(
                lambda: self._client.chat.completions.create(**kwargs)
            )
            
            tool_calls_buffer = {}
            chunk_count = 0
            usage_info = None
            # 单次等待下一个 chunk 的超时（秒）。若 LM Studio 报错但不断开连接，流可能挂起，超时后向前端返回错误并停止旋转。
            chunk_timeout = 90

            stream_iter = stream.__aiter__()
            try:
                finish_reason = None
                usage_info = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }

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
                    
                    choice = chunk.choices[0] if chunk.choices else None
                    delta = choice.delta if choice else None

                    if choice and choice.finish_reason:
                        finish_reason = choice.finish_reason
                        logger.info(f"Stream finish_reason: {finish_reason}, processed {chunk_count} chunks")

                    if delta and delta.content:
                        chunk_text = extract_text_from_content(delta.content)
                        if chunk_text:
                            logger.debug(f"Content chunk: {chunk_text[:50] if len(chunk_text) > 50 else chunk_text}")
                            # 累加到本地 token 计数器
                            token_counter.add_content(chunk_text)
                            yield {"type": "content", "content": chunk_text}
                
                    if delta and delta.tool_calls:
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
                
                    if choice and choice.finish_reason:
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
                                    # Handle arguments that might already be a dict or might be a JSON string
                                    args = tc["arguments"]
                                    if isinstance(args, str):
                                        args = json.loads(args)
                                    elif not isinstance(args, dict):
                                        # If it's neither a string nor a dict, convert to dict if possible
                                        try:
                                            args = dict(args)
                                        except Exception:
                                            pass  # Keep original if conversion fails
                                    tc["arguments"] = args
                                    tc["_truncated"] = False
                                except (json.JSONDecodeError, TypeError):
                                    logger.warning(f"Tool call '{tc['name']}' has invalid JSON arguments (truncated={truncated})")
                                    tc["arguments"] = {}
                                    tc["_truncated"] = True
                                yield {"type": "tool_call", "tool_call": tc}
                    
                        # 不在这里 yield finish，继续循环以捕获 usage chunk
                        # （DeepSeek/OpenAI 的 include_usage 模式会在 finish_reason 之后
                        #  发送一个独立的 usage chunk，choices=[]）
                        # finish 将在循环结束后 yield
                # 循环结束后，yield finish 事件（此时 usage_info 已被最终 chunk 填充）
                if finish_reason:
                    final_usage = usage_info
                    if not final_usage or (final_usage.get("total_tokens", 0) == 0):
                        # API 未返回 usage 或值全为 0，使用本地计算
                        local_usage = token_counter.finalize()
                        if local_usage.get("total_tokens", 0) > 0:
                            final_usage = local_usage
                            logger.info(f"Using local token count: {final_usage}")
                        elif final_usage:
                            logger.info(f"API returned usage: {final_usage}")
                    else:
                        logger.info(f"Using API usage info: {final_usage}")
                    
                    yield {"type": "finish", "finish_reason": finish_reason, "usage": final_usage}
                    # ── Track usage (stream) ──
                    _u = final_usage or {}
                    UsageTracker.shared().record_call(
                        model=self.config.model,
                        provider=self.config.provider,
                        prompt_tokens=_u.get("prompt_tokens", 0),
                        completion_tokens=_u.get("completion_tokens", 0),
                        total_tokens=_u.get("total_tokens", 0),
                        success=True,
                    )
            finally:
                # 确保流被正确关闭，防止连接泄漏
                try:
                    if hasattr(stream, 'aclose'):
                        await stream.aclose()
                    elif hasattr(stream, 'close'):
                        await stream.close()
                except Exception:
                    pass  # 忽略关闭时的错误
            
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
            # 上下文长度超限（context_length_exceeded / token limit / max context）
            # 标记为特殊错误类型，便于上层做上下文剪裁而非盲目重试
            _err_lower = err_msg.lower()
            if any(k in _err_lower for k in ("context_length", "context length", "token limit",
                                               "max_tokens", "maximum context", "too many tokens",
                                               "reduce the length", "context window")):
                err_msg = f"[CONTEXT_TOO_LARGE] 上下文超出模型窗口限制: {err_msg[:200]}"
                yield {"type": "error", "error": err_msg}
                UsageTracker.shared().record_call(
                    model=self.config.model,
                    provider=self.config.provider,
                    success=False,
                    error=err_msg[:200],
                )
                return
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
            # ── Track failed stream ──
            UsageTracker.shared().record_call(
                model=self.config.model,
                provider=self.config.provider,
                success=False,
                error=str(e)[:200],
            )
    
    async def simple_chat(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Simple chat without tools"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.chat(messages)
        return response.get("content", "")
