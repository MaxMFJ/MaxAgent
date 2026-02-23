"""
Mail Tool - 邮件操作
使用 macOS Mail.app 发送和管理邮件
"""

import asyncio
from typing import Optional, List
from .base import BaseTool, ToolResult, ToolCategory


class MailTool(BaseTool):
    """邮件工具，支持发送邮件、读取邮件等"""
    
    name = "mail"
    description = "邮件操作：发送邮件、读取收件箱、搜索邮件"
    category = ToolCategory.APPLICATION
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send", "read_inbox", "search", "count_unread", "open_compose"],
                "description": "操作类型"
            },
            "to": {
                "type": "string",
                "description": "收件人邮箱地址（多个用逗号分隔）"
            },
            "subject": {
                "type": "string",
                "description": "邮件主题"
            },
            "body": {
                "type": "string",
                "description": "邮件内容"
            },
            "cc": {
                "type": "string",
                "description": "抄送地址"
            },
            "bcc": {
                "type": "string",
                "description": "密送地址"
            },
            "search_query": {
                "type": "string",
                "description": "搜索关键词"
            },
            "count": {
                "type": "number",
                "description": "读取邮件数量，默认 5"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str,
        to: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        search_query: Optional[str] = None,
        count: int = 5
    ) -> ToolResult:
        """执行邮件操作"""
        
        if action == "send":
            return await self._send_mail(to, subject, body, cc, bcc)
        elif action == "read_inbox":
            return await self._read_inbox(count)
        elif action == "search":
            return await self._search_mail(search_query, count)
        elif action == "count_unread":
            return await self._count_unread()
        elif action == "open_compose":
            return await self._open_compose(to, subject, body)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _run_applescript(self, script: str) -> tuple[bool, str]:
        """执行 AppleScript"""
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return False, stderr.decode().strip()
            return True, stdout.decode().strip()
        except Exception as e:
            return False, str(e)
    
    async def _send_mail(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None
    ) -> ToolResult:
        """发送邮件"""
        if not to or not subject:
            return ToolResult(success=False, error="需要提供收件人和主题")
        
        # 转义特殊字符
        body_escaped = (body or "").replace('"', '\\"').replace('\n', '\\n')
        subject_escaped = subject.replace('"', '\\"')
        
        script = f'''
        tell application "Mail"
            set newMessage to make new outgoing message with properties {{subject:"{subject_escaped}", content:"{body_escaped}", visible:true}}
            
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{to}"}}
        '''
        
        if cc:
            script += f'''
                make new cc recipient at end of cc recipients with properties {{address:"{cc}"}}
            '''
        
        if bcc:
            script += f'''
                make new bcc recipient at end of bcc recipients with properties {{address:"{bcc}"}}
            '''
        
        script += '''
            end tell
            send newMessage
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={
                "message": "邮件已发送",
                "to": to,
                "subject": subject
            })
        return ToolResult(success=False, error=f"发送失败: {result}")
    
    async def _read_inbox(self, count: int) -> ToolResult:
        """读取收件箱最新邮件"""
        script = f'''
        tell application "Mail"
            set mailList to {{}}
            set inboxMessages to messages of inbox
            set messageCount to count of inboxMessages
            set readCount to {count}
            
            if messageCount < readCount then
                set readCount to messageCount
            end if
            
            repeat with i from 1 to readCount
                set msg to item i of inboxMessages
                set senderName to sender of msg
                set subjectText to subject of msg
                set dateReceived to date received of msg
                set isRead to read status of msg
                
                set end of mailList to {{senderName, subjectText, dateReceived as string, isRead}}
            end repeat
            
            return mailList
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"emails": result, "count": count})
        return ToolResult(success=False, error=result)
    
    async def _search_mail(self, query: str, count: int) -> ToolResult:
        """搜索邮件"""
        if not query:
            return ToolResult(success=False, error="需要提供搜索关键词")
        
        # 打开 Mail 并搜索
        script = f'''
        tell application "Mail"
            activate
            delay 0.5
        end tell
        
        tell application "System Events"
            tell process "Mail"
                keystroke "f" using command down
                delay 0.3
                keystroke "{query}"
            end tell
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={
                "message": f"已搜索: {query}",
                "note": "搜索结果显示在 Mail 应用中"
            })
        return ToolResult(success=False, error=result)
    
    async def _count_unread(self) -> ToolResult:
        """统计未读邮件数量"""
        script = '''
        tell application "Mail"
            set unreadCount to unread count of inbox
            return unreadCount
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            try:
                count = int(result)
                return ToolResult(success=True, data={"unread_count": count})
            except ValueError:
                return ToolResult(success=True, data={"unread_count": result})
        return ToolResult(success=False, error=result)
    
    async def _open_compose(
        self,
        to: Optional[str],
        subject: Optional[str],
        body: Optional[str]
    ) -> ToolResult:
        """打开邮件撰写窗口"""
        script = '''
        tell application "Mail"
            activate
            set newMessage to make new outgoing message with properties {visible:true}
        '''
        
        if to:
            script += f'''
            tell newMessage
                make new to recipient at end of to recipients with properties {{address:"{to}"}}
            end tell
            '''
        
        if subject:
            subject_escaped = subject.replace('"', '\\"')
            script += f'''
            set subject of newMessage to "{subject_escaped}"
            '''
        
        if body:
            body_escaped = body.replace('"', '\\"').replace('\n', '\\n')
            script += f'''
            set content of newMessage to "{body_escaped}"
            '''
        
        script += '''
        end tell
        '''
        
        success, result = await self._run_applescript(script)
        
        if success:
            return ToolResult(success=True, data={"message": "邮件撰写窗口已打开"})
        return ToolResult(success=False, error=result)
