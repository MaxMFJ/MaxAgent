"""
Notification Tool - 系统通知
"""

import asyncio
from typing import Optional
from .base import BaseTool, ToolResult, ToolCategory


class NotificationTool(BaseTool):
    """系统通知工具"""
    
    name = "notification"
    description = "发送系统通知、提醒"
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "schedule", "speak"],
                "description": "操作类型：send=发送通知, schedule=定时提醒, speak=语音朗读"
            },
            "title": {
                "type": "string",
                "description": "通知标题"
            },
            "message": {
                "type": "string",
                "description": "通知内容"
            },
            "subtitle": {
                "type": "string",
                "description": "副标题"
            },
            "sound": {
                "type": "string",
                "description": "通知声音名称"
            },
            "delay_seconds": {
                "type": "number",
                "description": "延迟秒数（用于定时提醒）"
            }
        },
        "required": ["action", "message"]
    }
    
    async def execute(
        self,
        action: str,
        message: str,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        sound: Optional[str] = None,
        delay_seconds: int = 0
    ) -> ToolResult:
        """执行通知操作"""
        
        if action == "send":
            return await self._send_notification(title, message, subtitle, sound)
        elif action == "schedule":
            return await self._schedule_notification(title, message, delay_seconds)
        elif action == "speak":
            return await self._speak(message)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _send_notification(
        self,
        title: Optional[str],
        message: str,
        subtitle: Optional[str],
        sound: Optional[str]
    ) -> ToolResult:
        """发送系统通知"""
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持系统通知")
        ok, err = await adapter.show_notification(
            title or "Chow Duck", message,
            subtitle=subtitle, sound=sound
        )
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={
            "message": "通知已发送",
            "title": title or "Chow Duck",
            "content": message
        })
    
    async def _schedule_notification(
        self,
        title: Optional[str],
        message: str,
        delay_seconds: int
    ) -> ToolResult:
        """定时发送通知"""
        if delay_seconds <= 0:
            return await self._send_notification(title, message, None, None)
        
        title = title or "Chow Duck 提醒"
        
        # 使用 at 命令或简单的延迟
        async def delayed_notify():
            await asyncio.sleep(delay_seconds)
            await self._send_notification(title, message, None, "default")
        
        # 启动后台任务
        asyncio.create_task(delayed_notify())
        
        return ToolResult(success=True, data={
            "message": f"已设置 {delay_seconds} 秒后提醒",
            "title": title,
            "content": message
        })
    
    async def _speak(self, message: str) -> ToolResult:
        """语音朗读（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return ToolResult(success=False, error="当前平台不支持语音朗读")
        ok, err = await self.runtime_adapter.speak(message)
        if not ok:
            return ToolResult(success=False, error=err)
        return ToolResult(success=True, data={"message": "已朗读", "text": message})
