"""
Application Control Tool
Open, close, and manage macOS applications
"""

import asyncio
import subprocess
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, ToolCategory


class AppTool(BaseTool):
    """Tool for controlling macOS applications"""
    
    name = "app_control"
    description = """macOS 应用控制工具，支持以下操作：
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
        cmd = ["open"]
        
        if url:
            cmd.append(url)
        elif file_path:
            cmd.extend([file_path])
            if app_name:
                cmd.extend(["-a", app_name])
        elif app_path:
            cmd.append(app_path)
        elif app_name:
            cmd.extend(["-a", app_name])
        else:
            return ToolResult(success=False, error="需要指定 app_name、app_path、url 或 file 之一")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode().strip())
        
        return ToolResult(success=True, data={"opened": app_name or app_path or url or file_path})
    
    async def _close_app(self, app_name: str) -> ToolResult:
        """Close an application gracefully"""
        script = f'''
        tell application "{app_name}"
            quit
        end tell
        '''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=f"无法关闭应用: {stderr.decode().strip()}")
        
        return ToolResult(success=True, data={"closed": app_name})
    
    async def _list_apps(self) -> ToolResult:
        """List running applications"""
        script = '''
        tell application "System Events"
            set appList to name of every process whose background only is false
        end tell
        return appList
        '''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode().strip())
        
        apps = stdout.decode().strip().split(", ")
        return ToolResult(success=True, data={"running_apps": apps, "count": len(apps)})
    
    async def _get_frontmost(self) -> ToolResult:
        """Get the frontmost application"""
        script = '''
        tell application "System Events"
            set frontApp to name of first process whose frontmost is true
        end tell
        return frontApp
        '''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode().strip())
        
        return ToolResult(success=True, data={"frontmost_app": stdout.decode().strip()})
    
    async def _hide_app(self, app_name: str) -> ToolResult:
        """Hide an application"""
        script = f'''
        tell application "System Events"
            set visible of process "{app_name}" to false
        end tell
        '''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode().strip())
        
        return ToolResult(success=True, data={"hidden": app_name})
    
    async def _activate_app(self, app_name: str) -> ToolResult:
        """Activate (bring to front) an application"""
        script = f'''
        tell application "{app_name}"
            activate
        end tell
        '''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            return ToolResult(success=False, error=stderr.decode().strip())
        
        return ToolResult(success=True, data={"activated": app_name})
