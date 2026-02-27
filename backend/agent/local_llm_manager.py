"""
Local LLM Service Manager
Automatically detects and switches between Ollama and LM Studio
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LocalLLMProvider(Enum):
    OLLAMA = "ollama"
    LM_STUDIO = "lmstudio"
    NONE = "none"


@dataclass
class LocalLLMConfig:
    provider: LocalLLMProvider
    base_url: str
    model: str
    api_key: str = "local"


# Default configurations
DEFAULT_CONFIGS = {
    LocalLLMProvider.OLLAMA: LocalLLMConfig(
        provider=LocalLLMProvider.OLLAMA,
        base_url="http://localhost:11434/v1",
        model="qwen2.5:7b",
        api_key="ollama"
    ),
    LocalLLMProvider.LM_STUDIO: LocalLLMConfig(
        provider=LocalLLMProvider.LM_STUDIO,
        base_url="http://localhost:1234/v1",
        model="",  # Will be detected
        api_key="lm-studio"
    )
}


class LocalLLMManager:
    """
    Manages local LLM services (Ollama, LM Studio)
    Detects all available services and picks the best model
    """

    def __init__(self):
        self._current_config: Optional[LocalLLMConfig] = None
        self._all_configs: list[LocalLLMConfig] = []
        self._client: Optional[AsyncOpenAI] = None
        self._last_check_time: float = 0
        self._check_interval: float = 30.0

    # 502 重试退避（秒）：本地服务启动或模型加载时常短暂返回 502，多等几秒再试
    _502_BACKOFF = (2.0, 5.0, 8.0)
    # 与浏览器/标准 API 客户端一致的请求头，避免部分本地服务对缺省头返回 502
    _API_HEADERS = {"Accept": "application/json", "User-Agent": "MacAgent-LocalLLM/1.0"}

    @staticmethod
    def _direct_local_url(url: str) -> str:
        """请求走直连：禁用代理，且 localhost 改为 127.0.0.1 避免代理/IPv6 导致 502（浏览器能访问、后端 502 时多为代理或解析差异）。"""
        u = url.replace("localhost", "127.0.0.1")
        return u

    async def check_ollama(self, url: str = "http://localhost:11434") -> list[LocalLLMConfig]:
        """Check Ollama and return configs for all available models (retry on 502 with backoff)."""
        url = self._direct_local_url(url)
        configs: list[LocalLLMConfig] = []
        for attempt in range(len(self._502_BACKOFF) + 1):
            try:
                async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                    response = await client.get(f"{url}/api/tags", headers=self._API_HEADERS)
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get("models", [])
                        for m in models:
                            name = m.get("name", "")
                            if name:
                                configs.append(LocalLLMConfig(
                                    provider=LocalLLMProvider.OLLAMA,
                                    base_url=f"{url}/v1",
                                    model=name,
                                    api_key="ollama",
                                ))
                        if configs:
                            logger.info(f"Ollama: {len(configs)} models ({', '.join(c.model for c in configs)})")
                        else:
                            logger.warning("Ollama running but no models available")
                        return configs
                    if response.status_code == 502 and attempt < len(self._502_BACKOFF):
                        delay = self._502_BACKOFF[attempt]
                        logger.debug("Ollama returned 502 (server/model may be starting), retry after %.0fs: %s", delay, (response.text or "")[:200])
                        await asyncio.sleep(delay)
                        continue
            except Exception as e:
                logger.debug(f"Ollama not available: {e}")
                if attempt < len(self._502_BACKOFF):
                    await asyncio.sleep(self._502_BACKOFF[attempt])
        return configs

    async def check_lm_studio(self, url: Optional[str] = None) -> list[LocalLLMConfig]:
        """Check LM Studio and return configs for all available models (retry on 502 with backoff). URL 来自配置（多端口时由 Mac 设置或 llm_config 指定），未配置时默认 1234。"""
        if url is None or url == "":
            try:
                from config.llm_config import get_lm_studio_base_url
                url = get_lm_studio_base_url()
            except Exception:
                url = "http://localhost:1234"
        base = self._direct_local_url(url).rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        configs: list[LocalLLMConfig] = []
        for attempt in range(len(self._502_BACKOFF) + 1):
            try:
                async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                    response = await client.get(f"{base}/models", headers=self._API_HEADERS)
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get("data", [])
                        for m in models:
                            mid = m.get("id", "")
                            if mid:
                                configs.append(LocalLLMConfig(
                                    provider=LocalLLMProvider.LM_STUDIO,
                                    base_url=base,
                                    model=mid,
                                    api_key="lm-studio",
                                ))
                        if configs:
                            logger.info(f"LM Studio: {len(configs)} models ({', '.join(c.model for c in configs)})")
                        else:
                            logger.warning("LM Studio running but no models loaded")
                        return configs
                    if response.status_code == 502 and attempt < len(self._502_BACKOFF):
                        delay = self._502_BACKOFF[attempt]
                        logger.debug("LM Studio returned 502 (server/model may be starting), retry after %.0fs: %s", delay, (response.text or "")[:200])
                        await asyncio.sleep(delay)
                        continue
            except Exception as e:
                logger.debug(f"LM Studio not available: {e}")
                if attempt < len(self._502_BACKOFF):
                    await asyncio.sleep(self._502_BACKOFF[attempt])
        return configs

    @staticmethod
    def _estimate_model_size(name: str) -> float:
        """Estimate model parameter size from name (higher = larger)"""
        import re
        name_lower = name.lower()
        match = re.search(r'(\d+\.?\d*)\s*b', name_lower)
        if match:
            return float(match.group(1))
        for marker, size in [("70b", 70), ("32b", 32), ("14b", 14), ("13b", 13),
                             ("8b", 8), ("7b", 7), ("3b", 3), ("1b", 1)]:
            if marker in name_lower:
                return size
        return 3.0

    @staticmethod
    def _is_chat_model(name: str) -> bool:
        """Filter out embedding/non-chat models"""
        skip = ("embed", "embedding", "nomic", "bge", "e5", "rerank")
        name_lower = name.lower()
        return not any(s in name_lower for s in skip)

    def _pick_best(self, configs: list[LocalLLMConfig]) -> Optional[LocalLLMConfig]:
        """Pick the best chat model: prefer larger, prefer qwen/deepseek"""
        chat_models = [c for c in configs if self._is_chat_model(c.model)]
        if not chat_models:
            return None
        def score(c: LocalLLMConfig) -> float:
            s = self._estimate_model_size(c.model)
            name = c.model.lower()
            if any(p in name for p in ("qwen", "deepseek")):
                s += 0.5
            return s
        return max(chat_models, key=score)

    async def detect_all_services(self) -> list[LocalLLMConfig]:
        """Detect Ollama and LM Studio concurrently, return all available models. LM Studio URL 从 llm_config 读取（支持多端口）。"""
        try:
            from config.llm_config import get_lm_studio_base_url
            lm_studio_url = get_lm_studio_base_url()
        except Exception:
            lm_studio_url = "http://localhost:1234"
        ollama_task = asyncio.create_task(self.check_ollama())
        lm_task = asyncio.create_task(self.check_lm_studio(url=lm_studio_url))
        ollama_configs, lm_configs = await asyncio.gather(ollama_task, lm_task)
        all_configs = ollama_configs + lm_configs
        self._all_configs = all_configs
        return all_configs

    def _get_preferred_local_model(self) -> Optional[str]:
        """Return user's preferred local model from llm_config if provider is local (ollama/lmstudio)."""
        try:
            from config.llm_config import load_llm_config
            cfg = load_llm_config()
            provider = (cfg.get("provider") or "").strip().lower()
            model = (cfg.get("model") or "").strip()
            if not model:
                return None
            if provider in ("ollama", "lmstudio", "lm_studio"):
                return model
            return None
        except Exception:
            return None

    async def detect_available_service(self) -> LocalLLMConfig:
        """Detect all local services and pick model: prefer user's saved choice, else best by size."""
        all_configs = await self.detect_all_services()
        preferred = self._get_preferred_local_model()
        chosen = None
        if preferred:
            for c in all_configs:
                if self._is_chat_model(c.model) and (c.model == preferred or c.model.endswith("/" + preferred)):
                    chosen = c
                    break
            if chosen:
                self._current_config = chosen
                logger.info(f"Using preferred local model: {chosen.provider.value}/{chosen.model}")
                return chosen
        best = self._pick_best(all_configs)
        if best:
            self._current_config = best
            logger.info(f"Best local model: {best.provider.value}/{best.model}")
            return best
        logger.warning("No local LLM service available (Ollama/LM Studio)")
        return LocalLLMConfig(provider=LocalLLMProvider.NONE, base_url="", model="", api_key="")

    async def get_client(self, force_refresh: bool = False) -> Tuple[Optional[AsyncOpenAI], LocalLLMConfig]:
        """Get an OpenAI-compatible client for the best available local LLM"""
        import time

        current_time = time.time()
        should_recheck = (
            force_refresh
            or self._current_config is None
            or self._current_config.provider == LocalLLMProvider.NONE
            or (current_time - self._last_check_time) > self._check_interval
        )

        if should_recheck:
            self._last_check_time = current_time
            config = await self.detect_available_service()

            if config.provider == LocalLLMProvider.NONE:
                self._client = None
                return None, config

            self._client = AsyncOpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
            )
            self._current_config = config

        return self._client, self._current_config

    @property
    def current_provider(self) -> LocalLLMProvider:
        if self._current_config:
            return self._current_config.provider
        return LocalLLMProvider.NONE

    @property
    def current_model(self) -> str:
        if self._current_config:
            return self._current_config.model
        return ""

    def get_status(self) -> Dict[str, Any]:
        """Get current status with all detected services"""
        all_services = []
        for c in self._all_configs:
            all_services.append({
                "provider": c.provider.value,
                "model": c.model,
                "base_url": c.base_url,
                "size_estimate": self._estimate_model_size(c.model),
            })
        return {
            "provider": self._current_config.provider.value if self._current_config else "none",
            "model": self._current_config.model if self._current_config else "",
            "base_url": self._current_config.base_url if self._current_config else "",
            "available": self._current_config is not None and self._current_config.provider != LocalLLMProvider.NONE,
            "all_services": all_services,
        }


# Global instance
_local_llm_manager: Optional[LocalLLMManager] = None


def get_local_llm_manager() -> LocalLLMManager:
    """Get or create the global local LLM manager"""
    global _local_llm_manager
    if _local_llm_manager is None:
        _local_llm_manager = LocalLLMManager()
    return _local_llm_manager


async def get_best_local_llm_client() -> Tuple[Optional[AsyncOpenAI], LocalLLMConfig]:
    """
    Convenience function to get the best available local LLM client
    """
    manager = get_local_llm_manager()
    return await manager.get_client()
