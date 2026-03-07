from .base import BaseTool
from .registry import ToolRegistry

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from runtime import RuntimeAdapter
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
from .request_tool_upgrade_tool import RequestToolUpgradeTool
from .evomap_tool import EvoMapTool
from .capsule_tool import CapsuleTool
from .mcp_catalog_tool import MCPCatalogTool, RequestMCPInstallTool
from .delegate_duck_tool import DelegateDuckTool
from .duck_status_tool import DuckStatusTool

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
    "RequestToolUpgradeTool",
    "EvoMapTool",
    "CapsuleTool",
    "MCPCatalogTool",
    "RequestMCPInstallTool",
    "DelegateDuckTool",
    "DuckStatusTool",
]

def get_all_tools(runtime_adapter: Optional["RuntimeAdapter"] = None):
    """
    Get instances of all available tools
    runtime_adapter: 由 Agent 注入，Tool 禁止自行获取
    """
    return [
        FileTool(runtime_adapter),
        TerminalTool(runtime_adapter),
        AppTool(runtime_adapter),
        SystemTool(runtime_adapter),
        ClipboardTool(runtime_adapter),
        ScriptTool(runtime_adapter),
        MultiScriptTool(runtime_adapter),
        ScreenshotTool(runtime_adapter),
        BrowserTool(runtime_adapter),
        MailTool(runtime_adapter),
        CalendarTool(runtime_adapter),
        NotificationTool(runtime_adapter),
        DockerTool(runtime_adapter),
        NetworkTool(runtime_adapter),
        DatabaseTool(runtime_adapter),
        DeveloperTool(runtime_adapter),
        WebSearchTool(),
        WikipediaTool(),
        DynamicToolGenerator(runtime_adapter),
        GUIAutomationTool(runtime_adapter),
        VisionTool(runtime_adapter),
        InputControlTool(runtime_adapter),
        RequestToolUpgradeTool(runtime_adapter),
        EvoMapTool(runtime_adapter),
        CapsuleTool(runtime_adapter),
        MCPCatalogTool(runtime_adapter),
        RequestMCPInstallTool(runtime_adapter),
        DelegateDuckTool(runtime_adapter),
        DuckStatusTool(runtime_adapter),
    ]
