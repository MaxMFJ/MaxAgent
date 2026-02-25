"""
Activation: reload generated tools
Stage: ACTIVATING
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_load_generated_tools: Optional[Callable[[], list]] = None


def set_load_generated_tools(fn: Callable[[], list]) -> None:
    global _load_generated_tools
    _load_generated_tools = fn


def activate() -> list:
    """
    Reload generated tools.
    Returns list of loaded tool names.
    """
    if _load_generated_tools:
        try:
            loaded = _load_generated_tools()
            logger.info(f"[Upgrade] Activated: {loaded}")
            return list(loaded) if loaded else []
        except Exception as e:
            logger.error(f"[Upgrade] Activation failed: {e}")
            return []
    logger.warning("[Upgrade] No load_generated_tools callback")
    return []
