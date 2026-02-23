from .base import BaseTool
from .registry import ToolRegistry
from .file_tool import FileTool
from .terminal_tool import TerminalTool
from .app_tool import AppTool
from .system_tool import SystemTool
from .clipboard_tool import ClipboardTool
from .script_tool import ScriptTool, MultiScriptTool
from .screenshot_tool import ScreenshotTool
from .browser_tool import BrowserTool
from .mail_tool import MailTool
from .calendar_tool import CalendarTool
from .notification_tool import NotificationTool
from .docker_tool import DockerTool
from .network_tool import NetworkTool
from .database_tool import DatabaseTool
from .developer_tool import DeveloperTool
from .web_search_tool import WebSearchTool, WikipediaTool
from .dynamic_tool_generator import DynamicToolGenerator, GUIAutomationTool
from .vision_tool import VisionTool
from .input_control_tool import InputControlTool

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "FileTool",
    "TerminalTool",
    "AppTool",
    "SystemTool",
    "ClipboardTool",
    "ScriptTool",
    "MultiScriptTool",
    "ScreenshotTool",
    "BrowserTool",
    "MailTool",
    "CalendarTool",
    "NotificationTool",
    "DockerTool",
    "NetworkTool",
    "DatabaseTool",
    "DeveloperTool",
    "WebSearchTool",
    "WikipediaTool",
    "DynamicToolGenerator",
    "GUIAutomationTool",
    "VisionTool",
    "InputControlTool",
]

def get_all_tools():
    """Get instances of all available tools"""
    return [
        FileTool(),
        TerminalTool(),
        AppTool(),
        SystemTool(),
        ClipboardTool(),
        ScriptTool(),
        MultiScriptTool(),
        ScreenshotTool(),
        BrowserTool(),
        MailTool(),
        CalendarTool(),
        NotificationTool(),
        DockerTool(),
        NetworkTool(),
        DatabaseTool(),
        DeveloperTool(),
        WebSearchTool(),
        WikipediaTool(),
        DynamicToolGenerator(),
        GUIAutomationTool(),
        VisionTool(),
        InputControlTool(),
    ]
