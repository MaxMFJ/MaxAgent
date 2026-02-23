"""
MockRuntimeAdapter - 测试用 Mock 适配器
无 GUI、无系统调用，用于 CI 与单元测试
"""

from typing import Dict, List, Optional, Set, Tuple

from .base import RuntimeAdapter, ScriptResult, CAP_APP_CONTROL, CAP_CLIPBOARD


class MockRuntimeAdapter(RuntimeAdapter):
    """
    无副作用 Mock 适配器
    - 所有操作返回成功或可配置的预设结果
    - 不调用 osascript、pbcopy、screencapture 等
    """
    
    def __init__(self, *, fail_caps: Optional[Set[str]] = None):
        self._fail_caps = fail_caps or set()
        self._clipboard = ""
        self._invocations: List[Dict] = []
    
    @property
    def platform(self) -> str:
        return "mock"
    
    @property
    def is_available(self) -> bool:
        return True
    
    def capabilities(self) -> Set[str]:
        return {
            CAP_APP_CONTROL, CAP_CLIPBOARD, "screenshot", "gui_input",
            "notification", "script", "browser", "window_info",
        }
    
    def _record(self, method: str, **kwargs):
        self._invocations.append({"method": method, **kwargs})
    
    async def open_app(self, app_name=None, app_path=None, url=None, file_path=None) -> Tuple[bool, str]:
        self._record("open_app", app_name=app_name, url=url)
        return True, ""
    
    async def close_app(self, app_name: str) -> Tuple[bool, str]:
        self._record("close_app", app_name=app_name)
        return True, ""
    
    async def activate_app(self, app_name: str) -> Tuple[bool, str]:
        self._record("activate_app", app_name=app_name)
        return True, ""
    
    async def list_apps(self) -> Tuple[bool, List[str], str]:
        return True, ["MockApp1", "MockApp2"], ""
    
    async def get_frontmost_app(self) -> Tuple[bool, str, str]:
        return True, "MockApp1", ""
    
    async def hide_app(self, app_name: str) -> Tuple[bool, str]:
        return True, ""
    
    async def clipboard_read(self) -> Tuple[bool, str, str]:
        return True, self._clipboard, ""
    
    async def clipboard_write(self, content: str) -> Tuple[bool, str]:
        self._clipboard = content
        self._record("clipboard_write", length=len(content))
        return True, ""
    
    async def screenshot_full(self, path: str) -> Tuple[bool, str]:
        self._record("screenshot_full", path=path)
        return True, ""
    
    async def screenshot_region(self, path: str, x: int, y: int, w: int, h: int) -> Tuple[bool, str]:
        self._record("screenshot_region", path=path, x=x, y=y, w=w, h=h)
        return True, ""
    
    async def screenshot_window(self, app_name: str, path: str) -> Tuple[bool, str]:
        self._record("screenshot_window", app_name=app_name, path=path)
        return True, ""
    
    async def mouse_move(self, x: int, y: int) -> Tuple[bool, str]:
        self._record("mouse_move", x=x, y=y)
        return True, ""
    
    async def mouse_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
        self._record("mouse_click", x=x, y=y)
        return True, ""
    
    async def type_text(self, text: str) -> Tuple[bool, str]:
        self._record("type_text", length=len(text))
        return True, ""
    
    async def get_window_info(self, app_name: str) -> Tuple[bool, Dict, str]:
        return True, {"name": "MockWindow", "width": 800, "height": 600}, ""
    
    async def run_script(self, script: str, lang: str = "applescript") -> ScriptResult:
        self._record("run_script", lang=lang, script_len=len(script))
        return ScriptResult(success=True, output="mock")
    
    async def show_notification(self, title: str, body: str, subtitle=None, sound=None) -> Tuple[bool, str]:
        self._record("show_notification", title=title, body=body)
        return True, ""
    
    def get_invocations(self) -> List[Dict]:
        """返回调用记录，用于断言"""
        return list(self._invocations)
