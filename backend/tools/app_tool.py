"""
Application Control Tool
Open, close, and manage applications（通过 RuntimeAdapter 跨平台）
"""

from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, ToolCategory


class AppTool(BaseTool):
    """Tool for controlling applications（应用控制）"""
    
    name = "app_control"
    description = """应用控制工具，支持以下操作：
- open: 打开应用程序
- close: 关闭应用程序
- list: 列出正在运行的应用
- frontmost: 获取当前最前面的应用
- hide: 隐藏应用
- activate: 激活（切换到）应用"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "close", "list", "frontmost", "hide", "activate"],
                "description": "要执行的操作"
            },
            "app_name": {
                "type": "string",
                "description": "应用程序名称（如 Safari, Finder, Terminal）"
            },
            "app_path": {
                "type": "string",
                "description": "应用程序完整路径（可选，用于 open 操作）"
            },
            "url": {
                "type": "string",
                "description": "要打开的 URL（用于 open 操作打开浏览器）"
            },
            "file": {
                "type": "string",
                "description": "要打开的文件路径（用于 open 操作）"
            }
        },
        "required": ["action"]
    }
    
    category = ToolCategory.APPLICATION
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        app_name = kwargs.get("app_name")
        app_path = kwargs.get("app_path")
        url = kwargs.get("url")
        file_path = kwargs.get("file")
        
        try:
            if action == "open":
                return await self._open_app(app_name, app_path, url, file_path)
            elif action == "close":
                if not app_name:
                    return ToolResult(success=False, error="关闭操作需要 app_name 参数")
                return await self._close_app(app_name)
            elif action == "list":
                return await self._list_apps()
            elif action == "frontmost":
                return await self._get_frontmost()
            elif action == "hide":
                if not app_name:
                    return ToolResult(success=False, error="隐藏操作需要 app_name 参数")
                return await self._hide_app(app_name)
            elif action == "activate":
                if not app_name:
                    return ToolResult(success=False, error="激活操作需要 app_name 参数")
                return await self._activate_app(app_name)
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _open_app(
        self,
        app_name: Optional[str],
        app_path: Optional[str],
        url: Optional[str],
        file_path: Optional[str]
    ) -> ToolResult:
        """Open an application, URL, or file"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, err = await adapter.open_app(app_name, app_path, url, file_path)
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"opened": app_name or app_path or url or file_path})
    
    async def _close_app(self, app_name: str) -> ToolResult:
        """Close an application gracefully"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, err = await adapter.close_app(app_name)
        if not ok:
            return ToolResult(success=False, error=err or "无法关闭应用")
        return ToolResult(success=True, data={"closed": app_name})
    
    async def _list_apps(self) -> ToolResult:
        """List running applications"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, apps, err = await adapter.list_apps()
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"running_apps": apps, "count": len(apps)})
    
    async def _get_frontmost(self) -> ToolResult:
        """Get the frontmost application"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, app_name, err = await adapter.get_frontmost_app()
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"frontmost_app": app_name})
    
    async def _hide_app(self, app_name: str) -> ToolResult:
        """Hide an application"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, err = await adapter.hide_app(app_name)
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"hidden": app_name})
    
    async def _activate_app(self, app_name: str) -> ToolResult:
        """Activate (bring to front) an application"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持应用控制")
        ok, err = await adapter.activate_app(app_name)
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"activated": app_name})
