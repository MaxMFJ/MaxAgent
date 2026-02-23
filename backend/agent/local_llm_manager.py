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
    Provides automatic detection and failover
    """
    
    def __init__(self):
        self._current_config: Optional[LocalLLMConfig] = None
        self._client: Optional[AsyncOpenAI] = None
        self._last_check_time: float = 0
        self._check_interval: float = 30.0  # Re-check every 30 seconds
    
    async def check_ollama(self, url: str = "http://localhost:11434") -> Tuple[bool, Optional[str]]:
        """
        Check if Ollama is running and get available models
        Returns (is_available, first_model_name)
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    if models:
                        # Prefer qwen or deepseek models
                        preferred = ["qwen", "deepseek", "llama"]
                        for pref in preferred:
                            for m in models:
                                if pref in m.get("name", "").lower():
                                    logger.info(f"Ollama available with model: {m['name']}")
                                    return True, m["name"]
                        # Return first available model
                        first_model = models[0].get("name", "")
                        logger.info(f"Ollama available with model: {first_model}")
                        return True, first_model
                    logger.warning("Ollama running but no models available")
                    return False, None
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
        return False, None
    
    async def check_lm_studio(self, url: str = "http://localhost:1234") -> Tuple[bool, Optional[str]]:
        """
        Check if LM Studio is running and get available models
        Returns (is_available, first_model_name)
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    if models:
                        first_model = models[0].get("id", "")
                        logger.info(f"LM Studio available with model: {first_model}")
                        return True, first_model
                    logger.warning("LM Studio running but no models loaded")
                    return False, None
        except Exception as e:
            logger.debug(f"LM Studio not available: {e}")
        return False, None
    
    async def detect_available_service(self) -> LocalLLMConfig:
        """
        Detect which local LLM service is available
        Priority: Ollama > LM Studio
        """
        # Check Ollama first
        ollama_ok, ollama_model = await self.check_ollama()
        if ollama_ok and ollama_model:
            config = LocalLLMConfig(
                provider=LocalLLMProvider.OLLAMA,
                base_url="http://localhost:11434/v1",
                model=ollama_model,
                api_key="ollama"
            )
            self._current_config = config
            return config
        
        # Check LM Studio
        lm_ok, lm_model = await self.check_lm_studio()
        if lm_ok and lm_model:
            config = LocalLLMConfig(
                provider=LocalLLMProvider.LM_STUDIO,
                base_url="http://localhost:1234/v1",
                model=lm_model,
                api_key="lm-studio"
            )
            self._current_config = config
            return config
        
        # No service available
        logger.warning("No local LLM service available (Ollama/LM Studio)")
        return LocalLLMConfig(
            provider=LocalLLMProvider.NONE,
            base_url="",
            model="",
            api_key=""
        )
    
    async def get_client(self, force_refresh: bool = False) -> Tuple[Optional[AsyncOpenAI], LocalLLMConfig]:
        """
        Get an OpenAI-compatible client for the available local LLM
        Returns (client, config)
        """
        import time
        
        current_time = time.time()
        should_recheck = (
            force_refresh or 
            self._current_config is None or
            self._current_config.provider == LocalLLMProvider.NONE or
            (current_time - self._last_check_time) > self._check_interval
        )
        
        if should_recheck:
            self._last_check_time = current_time
            config = await self.detect_available_service()
            
            if config.provider == LocalLLMProvider.NONE:
                self._client = None
                return None, config
            
            self._client = AsyncOpenAI(
                base_url=config.base_url,
                api_key=config.api_key
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
        """Get current status information"""
        return {
            "provider": self._current_config.provider.value if self._current_config else "none",
            "model": self._current_config.model if self._current_config else "",
            "base_url": self._current_config.base_url if self._current_config else "",
            "available": self._current_config is not None and self._current_config.provider != LocalLLMProvider.NONE
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
