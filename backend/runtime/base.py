"""
RuntimeAdapter - 运行时抽象基类
定义平台相关的系统能力接口，由各平台 Adapter 实现
支持能力声明（has_capability）用于语义层判断
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

# 能力常量（语义级，供 Core/Tools 通过 has_capability 查询）
CAP_APP_CONTROL = "app_control"
CAP_CLIPBOARD = "clipboard"
CAP_SCREENSHOT = "screenshot"
CAP_GUI_INPUT = "gui_input"
CAP_NOTIFICATION = "notification"
CAP_SCRIPT = "script"
CAP_BROWSER = "browser"
CAP_WINDOW_INFO = "window_info"


@dataclass
class ScriptResult:
    """脚本执行结果"""
    success: bool
    output: str = ""
    error: str = ""


class RuntimeAdapter(ABC):
    """
    运行时适配器基类
    
    各平台实现此类，提供系统能力：
    - 应用控制、剪贴板、截图、GUI 输入
    - 脚本执行（Mac: AppleScript, Linux: bash, Windows: PowerShell）
    """
    
    @property
    @abstractmethod
    def platform(self) -> str:
        """平台标识: mac, linux, windows"""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """当前平台是否支持此适配器"""
        pass
    
    def has_capability(self, cap: str) -> bool:
        """
        语义级能力声明
        子类可覆盖，声明支持的能力，避免 Core 依赖坐标驱动等平台细节
        """
        return cap in self.capabilities()
    
    def capabilities(self) -> Set[str]:
        """返回此适配器支持的能力集合，子类覆盖"""
        return set()
    
    # ---------- 应用控制 ----------
    
    @abstractmethod
    async def open_app(
        self,
        app_name: Optional[str] = None,
        app_path: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> Tuple[bool, str]:
        """打开应用/URL/文件。返回 (success, error_message)"""
        pass
    
    @abstractmethod
    async def close_app(self, app_name: str) -> Tuple[bool, str]:
        """关闭应用"""
        pass
    
    @abstractmethod
    async def activate_app(self, app_name: str) -> Tuple[bool, str]:
        """激活/切换到应用"""
        pass
    
    async def list_apps(self) -> Tuple[bool, List[str], str]:
        """列出运行中的应用。返回 (success, app_names, error_message)"""
        return False, [], "未实现"
    
    async def get_frontmost_app(self) -> Tuple[bool, str, str]:
        """获取最前面的应用。返回 (success, app_name, error_message)"""
        return False, "", "未实现"
    
    async def hide_app(self, app_name: str) -> Tuple[bool, str]:
        """隐藏应用"""
        return False, "未实现"
    
    # ---------- 剪贴板 ----------
    
    @abstractmethod
    async def clipboard_read(self) -> Tuple[bool, str, str]:
        """读取剪贴板。返回 (success, content, error_message)"""
        pass
    
    @abstractmethod
    async def clipboard_write(self, content: str) -> Tuple[bool, str]:
        """写入剪贴板。返回 (success, error_message)"""
        pass
    
    # ---------- 截图 ----------
    
    async def screenshot_full(self, path: str) -> Tuple[bool, str]:
        """全屏截图到 path"""
        return False, "未实现"
    
    async def screenshot_region(
        self, path: str, x: int, y: int, width: int, height: int
    ) -> Tuple[bool, str]:
        """区域截图"""
        return False, "未实现"
    
    async def screenshot_window(self, app_name: str, path: str) -> Tuple[bool, str]:
        """应用窗口截图（若平台支持）"""
        return False, "未实现"
    
    async def screenshot_interactive(self, path: str) -> Tuple[bool, str]:
        """交互式区域选择截图（-i，需用户操作）"""
        return False, "未实现"
    
    async def screenshot_pick_window(self, path: str) -> Tuple[bool, str]:
        """交互式窗口选择截图（-w，需用户点击窗口）"""
        return False, "未实现"
    
    # ---------- GUI 输入 ----------
    
    async def mouse_move(self, x: int, y: int) -> Tuple[bool, str]:
        """移动鼠标"""
        return False, "未实现"
    
    async def mouse_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
        """点击（可选坐标，否则用当前位置）"""
        return False, "未实现"
    
    async def type_text(self, text: str) -> Tuple[bool, str]:
        """输入文本"""
        return False, "未实现"
    
    async def get_window_info(self, app_name: str) -> Tuple[bool, Dict, str]:
        """获取窗口信息（位置、大小等）"""
        return False, {}, "未实现"
    
    # ---------- 脚本执行 ----------
    
    @abstractmethod
    async def run_script(self, script: str, lang: str = "applescript") -> ScriptResult:
        """
        执行脚本
        lang: applescript | bash | python | powershell（由平台决定支持）
        """
        pass
    
    # ---------- 通知 ----------
    
    async def show_notification(
        self, title: str, body: str,
        subtitle: Optional[str] = None,
        sound: Optional[str] = None
    ) -> Tuple[bool, str]:
        """显示系统通知"""
        return False, "未实现"
    
    async def speak(self, text: str) -> Tuple[bool, str]:
        """语音朗读（若平台支持）"""
        return False, "未实现"
