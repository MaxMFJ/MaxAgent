"""
WindowsRuntimeAdapter - Windows 运行时适配器（占位，待实现）
扩展点：实现后可在此完成 pyautogui、ctypes Win32 API 等集成
"""

import platform
from typing import List, Optional, Tuple

from .base import RuntimeAdapter, ScriptResult


class WindowsRuntimeAdapter(RuntimeAdapter):
    """Windows 平台运行时适配器（占位）"""
    
    @property
    def platform(self) -> str:
        return "windows"
    
    @property
    def is_available(self) -> bool:
        return platform.system() == "Windows"
    
    async def open_app(self, app_name=None, app_path=None, url=None, file_path=None) -> Tuple[bool, str]:
        return False, "Windows 适配器待实现"
    
    async def close_app(self, app_name: str) -> Tuple[bool, str]:
        return False, "Windows 适配器待实现"
    
    async def activate_app(self, app_name: str) -> Tuple[bool, str]:
        return False, "Windows 适配器待实现"
    
    async def clipboard_read(self) -> Tuple[bool, str, str]:
        return False, "", "Windows 适配器待实现"
    
    async def clipboard_write(self, content: str) -> Tuple[bool, str]:
        return False, "Windows 适配器待实现"
    
    async def run_script(self, script: str, lang: str = "powershell") -> ScriptResult:
        return ScriptResult(success=False, error="Windows 适配器待实现")
