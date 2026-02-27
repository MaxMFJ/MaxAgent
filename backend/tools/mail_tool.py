"""
Mail Tool - 邮件操作
发送邮件：通过 SMTP 系统级发送（不依赖 Mail.app）
读邮件/搜索：仍使用 Mail.app（需已配置）
"""

import asyncio
import os
import time
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from .base import BaseTool, ToolResult, ToolCategory


class MailTool(BaseTool):
    """邮件工具：系统级 SMTP 发送，可选 Mail.app 读/搜"""
    
    name = "mail"
    description = "邮件操作：通过 SMTP 系统级发送邮件（不依赖 Mail 程序），可选读取收件箱、搜索"
    category = ToolCategory.SYSTEM
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
        """执行 AppleScript（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return False, "当前平台不支持 AppleScript"
        r = await self.runtime_adapter.run_script(script, lang="applescript")
        return r.success, r.output if r.success else r.error
    
    def _get_smtp_config(self) -> tuple[Optional[str], int, Optional[str], Optional[str]]:
        """从 smtp_config 读取（支持 Mac 设置页 + 环境变量）"""
        try:
            from config.smtp_config import get_smtp_config
            return get_smtp_config()
        except ImportError:
            pass
        server = os.environ.get("MACAGENT_SMTP_SERVER")
        port = int(os.environ.get("MACAGENT_SMTP_PORT", "465"))
        user = os.environ.get("MACAGENT_SMTP_USER")
        password = os.environ.get("MACAGENT_SMTP_PASSWORD")
        return server, port, user, password

    async def _send_mail(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None
    ) -> ToolResult:
        """通过 SMTP 系统级发送邮件（不依赖 Mail.app）"""
        if not to or not subject:
            return ToolResult(success=False, error="需要提供收件人和主题")
        
        server, port, user, password = self._get_smtp_config()
        if not all([server, user, password]):
            return ToolResult(
                success=False,
                error="请先在 Mac 设置 → 邮件 中填写邮箱与授权码，或配置环境变量 MACAGENT_SMTP_SERVER / MACAGENT_SMTP_USER / MACAGENT_SMTP_PASSWORD"
            )

        def _do_send() -> tuple[bool, str]:
            timeout = 30
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = user
            msg["To"] = to
            if cc:
                msg["Cc"] = cc
            if bcc:
                msg["Bcc"] = bcc
            msg.attach(MIMEText(body or "", "plain", "utf-8"))
            recipients = [addr.strip() for addr in to.split(",")]
            if cc:
                recipients.extend(addr.strip() for addr in cc.split(","))
            if bcc:
                recipients.extend(addr.strip() for addr in bcc.split(","))
            context = ssl.create_default_context()

            def _try_465() -> tuple[bool, str]:
                try:
                    with smtplib.SMTP_SSL(server, 465, context=context, timeout=timeout) as s:
                        s.login(user, password)
                        s.sendmail(user, recipients, msg.as_string())
                    return True, ""
                except Exception as e:
                    return False, str(e)

            def _try_587() -> tuple[bool, str]:
                try:
                    with smtplib.SMTP(server, 587, timeout=timeout) as s:
                        s.ehlo()
                        s.starttls(context=context)
                        s.ehlo()
                        s.login(user, password)
                        s.sendmail(user, recipients, msg.as_string())
                    return True, ""
                except Exception as e:
                    return False, str(e)

            if port == 465:
                ok, err = _try_465()
                if ok:
                    return True, ""
                err_lower = (err or "").lower()
                if any(k in err_lower for k in ("timeout", "ssl", "timed out", "handshake", "connection")):
                    time.sleep(2)  # 稍等后重试，缓解瞬时超时
                    ok, err2 = _try_587()
                    if ok:
                        return True, ""
                    return False, f"465 失败: {err}；587 也失败: {err2}"
                return False, err
            else:
                ok, err = _try_587()
                if ok:
                    return True, ""
                err_lower = (err or "").lower()
                if any(k in err_lower for k in ("timeout", "ssl", "timed out", "handshake", "connection")):
                    time.sleep(2)
                    ok, err2 = _try_465()
                    if ok:
                        return True, ""
                    return False, f"587 失败: {err}；465 也失败: {err2}"
                return False, err

        success, err = await asyncio.get_event_loop().run_in_executor(None, _do_send)
        if success:
            return ToolResult(success=True, data={
                "message": "邮件已通过 SMTP 发送",
                "to": to,
                "subject": subject
            })
        # 区分错误类型，便于 LLM 正确引导
        err_lower = (err or "").lower()
        is_connection = any(k in err_lower for k in ("timeout", "ssl", "timed out", "handshake", "connection", "connect"))
        if is_connection:
            return ToolResult(
                success=False,
                error=f"SMTP 连接失败（配置已就绪，疑似网络/防火墙问题）：{err}。建议稍后重试，或运行 backend/scripts/test_smtp_send.py 诊断"
            )
        return ToolResult(success=False, error=f"SMTP 发送失败: {err}")
    
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
