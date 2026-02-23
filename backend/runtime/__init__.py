"""
Runtime Abstraction Layer - 运行时抽象层
平台无关的 Agent 通过此层调用系统能力，便于移植到 Linux/Windows

架构:
  Core Agent
      ↓
  RuntimeAdapter (本模块)
      ↓
  MacAdapter / LinuxAdapter / WindowsAdapter / MockAdapter
"""

from .base import (
    RuntimeAdapter, ScriptResult,
    CAP_APP_CONTROL, CAP_CLIPBOARD, CAP_SCREENSHOT, CAP_GUI_INPUT,
    CAP_NOTIFICATION, CAP_SCRIPT, CAP_BROWSER, CAP_WINDOW_INFO,
)
from .registry import (
    get_runtime_adapter,
    get_runtime_adapter_for_test,
    current_platform,
    register,
    list_registered,
)

__all__ = [
    "RuntimeAdapter",
    "ScriptResult",
    "get_runtime_adapter",
    "get_runtime_adapter_for_test",
    "current_platform",
    "register",
    "list_registered",
    "CAP_APP_CONTROL", "CAP_CLIPBOARD", "CAP_SCREENSHOT", "CAP_GUI_INPUT",
    "CAP_NOTIFICATION", "CAP_SCRIPT", "CAP_BROWSER", "CAP_WINDOW_INFO",
]
