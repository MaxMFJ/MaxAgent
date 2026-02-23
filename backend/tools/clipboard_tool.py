"""
Clipboard Tool
Read and write to system clipboard（通过 RuntimeAdapter 跨平台）
"""

from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, ToolCategory


class ClipboardTool(BaseTool):
    """Tool for clipboard operations（剪贴板操作）"""
    
    name = "clipboard"
    description = """剪贴板操作工具，支持以下操作：
- read: 读取剪贴板内容
- write: 写入内容到剪贴板
- clear: 清空剪贴板"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "clear"],
                "description": "要执行的操作"
            },
            "content": {
                "type": "string",
                "description": "要写入剪贴板的内容（仅用于 write 操作）"
            }
        },
        "required": ["action"]
    }
    
    category = ToolCategory.CLIPBOARD
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        content = kwargs.get("content")
        
        try:
            if action == "read":
                return await self._read()
            elif action == "write":
                if content is None:
                    return ToolResult(success=False, error="写入操作需要 content 参数")
                return await self._write(content)
            elif action == "clear":
                return await self._clear()
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _read(self) -> ToolResult:
        """Read text from clipboard"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持剪贴板操作")
        ok, content, err = await adapter.clipboard_read()
        if not ok:
            return ToolResult(success=False, error=err or "读取剪贴板失败")
        return ToolResult(success=True, data={
            "content": content,
            "length": len(content)
        })
    
    async def _write(self, content: str) -> ToolResult:
        """Write text to clipboard"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持剪贴板操作")
        ok, err = await adapter.clipboard_write(content)
        if not ok:
            return ToolResult(success=False, error=err or "写入剪贴板失败")
        return ToolResult(success=True, data={
            "written": True,
            "length": len(content)
        })
    
    async def _clear(self) -> ToolResult:
        """Clear clipboard by writing empty string"""
        return await self._write("")
