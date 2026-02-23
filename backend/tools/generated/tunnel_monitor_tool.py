import asyncio
import json
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import logging

from tools.base import BaseTool, ToolResult, ToolCategory
from tools.cloudflared_utils import (
    CLOUDFLARED_METRICS_PORT,
    get_cloudflared_restart_command,
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TunnelMonitorTool(BaseTool):
    name = "tunnel_monitor"
    description = """监控 cloudflared 隧道连接，中断后自动重启并邮件通知。与 Mac 客户端、tunnel_manager 共用同一 cloudflared 隧道（用户连接通道）。"""
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "email_recipient": {
                "type": "string",
                "description": "收件人邮箱地址",
                "default": "675632487@qq.com"
            },
            "check_interval": {
                "type": "integer",
                "description": "检查间隔时间（秒）",
                "default": 30
            },
            "max_retries": {
                "type": "integer",
                "description": "最大重试次数",
                "default": 3
            },
            "tunnel_process_name": {
                "type": "string",
                "description": "隧道进程名称（用于检查进程是否存在），如 cloudflared、frpc",
                "default": "cloudflared"
            },
            "tunnel_port": {
                "type": "integer",
                "description": "隧道监听端口（cloudflared 为 4040，frpc 通常为 7000）",
                "default": 4040
            },
            "restart_command": {
                "type": "string",
                "description": "重启 cloudflared 命令，留空则自动使用与 Mac 客户端一致的命令",
                "default": ""
            },
            "get_tunnel_url_command": {
                "type": "string",
                "description": "获取隧道 URL 的命令，留空则 curl localhost:4040/api/tunnels",
                "default": ""
            },
            "smtp_server": {
                "type": "string",
                "description": "SMTP服务器地址",
                "default": "smtp.qq.com"
            },
            "smtp_port": {
                "type": "integer",
                "description": "SMTP服务器端口",
                "default": 465
            },
            "smtp_username": {
                "type": "string",
                "description": "SMTP用户名（发件人邮箱）",
                "default": "your_email@qq.com"
            },
            "smtp_password": {
                "type": "string",
                "description": "SMTP密码或授权码",
                "default": "your_password"
            }
        },
        "required": []
    }

    def __init__(self):
        super().__init__()
        self.monitoring = False
        self.monitor_task = None

    async def check_tunnel_status(self, process_name: str, port: int) -> bool:
        """检查隧道状态：进程是否存在且端口是否监听"""
        try:
            # 检查进程是否存在
            check_process_cmd = f"pgrep -f {process_name}"
            proc = await asyncio.create_subprocess_shell(
                check_process_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.warning(f"进程 {process_name} 不存在")
                return False
            
            # 检查端口是否监听
            check_port_cmd = f"lsof -i :{port} | grep LISTEN"
            proc = await asyncio.create_subprocess_shell(
                check_port_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0 or not stdout:
                logger.warning(f"端口 {port} 未监听")
                return False
            
            logger.info(f"隧道状态正常: 进程 {process_name} 运行中, 端口 {port} 监听中")
            return True
            
        except Exception as e:
            logger.error(f"检查隧道状态时出错: {e}")
            return False

    async def restart_tunnel(self, restart_command: str, max_retries: int) -> bool:
        """重启隧道服务"""
        for attempt in range(max_retries):
            try:
                logger.info(f"尝试重启隧道 (第 {attempt + 1} 次)")
                
                proc = await asyncio.create_subprocess_shell(
                    restart_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    logger.info("隧道重启成功")
                    # 等待 cloudflared 启动并完成注册（与 Mac 客户端同一通道）
                    await asyncio.sleep(8)
                    return True
                else:
                    logger.warning(f"重启失败: {stderr.decode()}")
                    
            except Exception as e:
                logger.error(f"重启隧道时出错: {e}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 指数退避
        
        logger.error(f"隧道重启失败，已达到最大重试次数 {max_retries}")
        return False

    async def get_tunnel_url(
        self, get_tunnel_url_command: str, max_retries: int = 5, retry_delay: float = 3.0
    ) -> Optional[str]:
        """获取隧道公网 URL（cloudflared 启动后需数秒才能拿到 URL，支持重试）"""
        for attempt in range(max_retries):
            try:
                proc = await asyncio.create_subprocess_shell(
                    get_tunnel_url_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                out_s = stdout.decode().strip()
                err_s = stderr.decode().strip()

                if proc.returncode == 0 and out_s:
                    # 尝试解析 cloudflared metrics API JSON
                    try:
                        data = json.loads(out_s)
                        if "tunnels" in data and data["tunnels"]:
                            for t in data["tunnels"]:
                                if t.get("public_url"):
                                    return t["public_url"]
                    except json.JSONDecodeError:
                        urls = re.findall(r"https?://[^\s\"]+", out_s)
                        if urls:
                            return urls[0]
                    logger.warning("无法从输出中解析隧道 URL")
                    return "http://tunnel.example.com"
                else:
                    if attempt < max_retries - 1:
                        logger.info(
                            f"获取隧道 URL 第 {attempt + 1}/{max_retries} 次失败，{retry_delay}s 后重试"
                        )
                        await asyncio.sleep(retry_delay)
                        continue
                    logger.warning(
                        f"获取隧道URL命令失败 (code={proc.returncode}): stdout={out_s[:200]!r} stderr={err_s[:200]!r}"
                    )
            except Exception as e:
                logger.error(f"获取隧道URL时出错: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
        return "http://tunnel.example.com"

    async def send_email_notification(
        self,
        recipient: str,
        tunnel_url: str,
        smtp_server: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str
    ) -> bool:
        """发送邮件通知"""
        try:
            # 创建邮件内容
            message = MIMEMultipart("alternative")
            message["Subject"] = "隧道链接更新通知"
            message["From"] = smtp_username
            message["To"] = recipient
            
            # 邮件正文
            text = f"""
            隧道链接已更新！
            
            新的隧道链接: {tunnel_url}
            更新时间: {asyncio.get_event_loop().time()}
            状态: 隧道已重启并正常运行
            
            请使用新的链接访问服务。
            """
            
            html = f"""
            <html>
            <body>
                <h2>隧道链接更新通知</h2>
                <p><strong>新的隧道链接:</strong> <a href="{tunnel_url}">{tunnel_url}</a></p>
                <p><strong>更新时间:</strong> {asyncio.get_event_loop().time()}</p>
                <p><strong>状态:</strong> 隧道已重启并正常运行</p>
                <p>请使用新的链接访问服务。</p>
            </body>
            </html>
            """
            
            # 添加文本和HTML版本
            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            message.attach(part1)
            message.attach(part2)
            
            # 创建SSL上下文并发送邮件
            context = ssl.create_default_context()
            
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(smtp_username, smtp_password)
                server.sendmail(smtp_username, recipient, message.as_string())
            
            logger.info(f"邮件已发送到 {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"发送邮件时出错: {e}")
            return False

    async def monitor_loop(
        self,
        email_recipient: str,
        check_interval: int,
        max_retries: int,
        tunnel_process_name: str,
        tunnel_port: int,
        restart_command: str,
        get_tunnel_url_command: str,
        smtp_server: str,
        smtp_port: int,
        smtp_username: str,
        smtp_password: str
    ):
        """监控循环"""
        logger.info(f"开始监控隧道，检查间隔: {check_interval}秒")
        
        while self.monitoring:
            try:
                # 检查隧道状态
                is_healthy = await self.check_tunnel_status(tunnel_process_name, tunnel_port)
                
                if not is_healthy:
                    logger.warning("检测到隧道中断，开始重启流程...")
                    
                    # 重启隧道
                    restart_success = await self.restart_tunnel(restart_command, max_retries)
                    
                    if restart_success:
                        # 获取新的隧道URL
                        tunnel_url = await self.get_tunnel_url(get_tunnel_url_command)
                        
                        # 发送邮件通知
                        email_sent = await self.send_email_notification(
                            email_recipient,
                            tunnel_url,
                            smtp_server,
                            smtp_port,
                            smtp_username,
                            smtp_password
                        )
                        
                        if email_sent:
                            logger.info("隧道重启并通知完成")
                        else:
                            logger.warning("隧道重启成功，但邮件发送失败")
                    else:
                        logger.error("隧道重启失败，需要手动干预")
                
                # 等待下一次检查
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                logger.info("监控循环被取消")
                break
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
                await asyncio.sleep(check_interval)

    async def execute(self, **kwargs) -> ToolResult:
        """执行隧道监控工具（与 Mac 客户端、tunnel_manager 同一 cloudflared 通道）"""
        try:
            email_recipient = kwargs.get("email_recipient", "675632487@qq.com")
            check_interval = kwargs.get("check_interval", 30)
            max_retries = kwargs.get("max_retries", 3)
            tunnel_process_name = kwargs.get("tunnel_process_name", "cloudflared")
            tunnel_port = kwargs.get("tunnel_port", CLOUDFLARED_METRICS_PORT)
            restart_command = kwargs.get("restart_command") or get_cloudflared_restart_command()
            get_tunnel_url_command = (
                kwargs.get("get_tunnel_url_command")
                or f"curl -s http://localhost:{CLOUDFLARED_METRICS_PORT}/api/tunnels"
            )
            smtp_server = kwargs.get('smtp_server', 'smtp.qq.com')
            smtp_port = kwargs.get('smtp_port', 465)
            smtp_username = kwargs.get('smtp_username', 'your_email@qq.com')
            smtp_password = kwargs.get('smtp_password', 'your_password')
            
            # 如果已经在监控，则停止之前的监控
            if self.monitoring and self.monitor_task:
                self.monitoring = False
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
            
            # 启动新的监控
            self.monitoring = True
            self.monitor_task = asyncio.create_task(
                self.monitor_loop(
                    email_recipient=email_recipient,
                    check_interval=check_interval,
                    max_retries=max_retries,
                    tunnel_process_name=tunnel_process_name,
                    tunnel_port=tunnel_port,
                    restart_command=restart_command,
                    get_tunnel_url_command=get_tunnel_url_command,
                    smtp_server=smtp_server,
                    smtp_port=smtp_port,
                    smtp_username=smtp_username,
                    smtp_password=smtp_password
                )
            )
            
            return ToolResult(
                success=True,
                data={
                    "message": "隧道监控已启动",
                    "email_recipient": email_recipient,
                    "check_interval": check_interval,
                    "max_retries": max_retries,
                    "monitoring": True
                }
            )
            
        except Exception as e:
            logger.error(f"执行隧道监控工具时出错: {e}")
            return ToolResult(
                success=False,
                error=f"启动监控失败: {str(e)}",
                data={"monitoring": False}
            )

    async def stop_monitoring(self) -> ToolResult:
        """停止监控"""
        try:
            if self.monitoring and self.monitor_task:
                self.monitoring = False
                self.monitor_task.cancel()
                try:
                    await self.monitor_task
                except asyncio.CancelledError:
                    pass
                
                return ToolResult(
                    success=True,
                    data={
                        "message": "隧道监控已停止",
                        "monitoring": False
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    data={
                        "message": "隧道监控未运行",
                        "monitoring": False
                    }
                )
                
        except Exception as e:
            logger.error(f"停止监控时出错: {e}")
            return ToolResult(
                success=False,
                error=f"停止监控失败: {str(e)}",
                data={"monitoring": False}
            )