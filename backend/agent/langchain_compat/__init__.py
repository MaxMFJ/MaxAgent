"""
LangChain 兼容层（部分引入）
- 将 MacAgent 的 LLMClient 适配为 LangChain BaseChatModel，工具适配为 LangChain BaseTool
- 兼容模式下可使用 LangChain 的 create_tool_calling_agent、LCEL、流式与可观测能力
- 未安装 langchain 时本模块可用但 run_stream 等会提示安装依赖
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 运行时是否启用 LangChain 兼容模式（配置 > 环境变量 > 默认 true）
def is_langchain_compat_enabled() -> bool:
    try:
        from app_state import get_langchain_compat_enabled
        return get_langchain_compat_enabled()
    except Exception:
        import os
        return os.environ.get("ENABLE_LANGCHAIN_COMPAT", "true").lower() in ("true", "1", "yes")


def _check_langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401
        import langchain  # noqa: F401
        return True
    except ImportError:
        return False


LANGCHAIN_AVAILABLE = _check_langchain_available()

if LANGCHAIN_AVAILABLE:
    try:
        from .llm_adapter import MacAgentChatModel
        from .tool_adapter import mac_tools_to_langchain
        from .runner import LangChainChatRunner
        from .memory_adapter import MacAgentMemoryAdapter
        _exports = [
            "MacAgentChatModel",
            "mac_tools_to_langchain",
            "LangChainChatRunner",
            "MacAgentMemoryAdapter",
        ]
    except Exception as e:
        logger.warning("LangChain compat submodules failed to load: %s", e)
        MacAgentChatModel = None  # type: ignore
        mac_tools_to_langchain = None  # type: ignore
        LangChainChatRunner = None  # type: ignore
        MacAgentMemoryAdapter = None  # type: ignore
        _exports = []
    __all__ = _exports + [
        "is_langchain_compat_enabled",
        "LANGCHAIN_AVAILABLE",
        "get_langchain_chat_runner",
    ]
else:
    MacAgentChatModel = None  # type: ignore
    mac_tools_to_langchain = None  # type: ignore
    LangChainChatRunner = None  # type: ignore
    MacAgentMemoryAdapter = None  # type: ignore
    __all__ = [
        "is_langchain_compat_enabled",
        "LANGCHAIN_AVAILABLE",
        "get_langchain_chat_runner",
    ]


def get_langchain_chat_runner(
    llm_client: Any,
    registry: Any,
    context_manager: Any,
    runtime_adapter: Any = None,
    system_prompt_fn: Optional[Any] = None,
) -> Optional[Any]:
    """
    获取 LangChain 兼容的 Chat Runner（需已安装 langchain 且启用 ENABLE_LANGCHAIN_COMPAT）。
    返回 None 表示不可用。
    """
    if not LANGCHAIN_AVAILABLE or not is_langchain_compat_enabled():
        return None
    try:
        from .runner import LangChainChatRunner
    except Exception:
        return None
    if LangChainChatRunner is None:
        return None
    return LangChainChatRunner(
        llm_client=llm_client,
        registry=registry,
        context_manager=context_manager,
        runtime_adapter=runtime_adapter,
        system_prompt_fn=system_prompt_fn,
    )
