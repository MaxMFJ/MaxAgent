import asyncio
import json
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional

from tools.base import BaseTool, ToolResult, ToolCategory, ToolException


class InteractiveMailTool(BaseTool):
    name = "interactive_mail"
    description = "通过Chat交互获取SMTP配置信息后发送邮件。当缺少SMTP服务器、邮箱、授权码等信息时，会提示用户通过Chat提供，然后自动配置并发送邮件。"
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "to_email": {
                "type": "string",
                "description": "收件人邮箱地址"
            },
            "subject": {
                "type": "string",
                "description": "邮件主题"
            },
            "body": {
                "type": "string",
                "description": "邮件正文内容"
            },
            "smtp_server": {
                "type": "string",
                "description": "SMTP服务器地址（如smtp.qq.com），可选，缺失时会提示用户提供"
            },
            "smtp_port": {
                "type": "integer",
                "description": "SMTP端口号（如465或587），可选，缺失时会提示用户提供"
            },
            "sender_email": {
                "type": "string",
                "description": "发件人邮箱地址，可选，缺失时会提示用户提供"
            },
            "sender_password": {
                "type": "string",
                "description": "发件人邮箱授权码/密码，可选，缺失时会提示用户提供"
            }
        },
        "required": [
            "to_email",
            "subject",
            "body"
        ]
    }

    def __init__(self):
        super().__init__()
        self.config_file = "tools/generated/smtp_config.json"

    def _validate_smtp_config(self, config: Dict[str, Any]) -> None:
        """验证SMTP配置是否完整"""
        required_fields = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password']
        missing_fields = [field for field in required_fields if not config.get(field)]

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            raise ToolException(
                f"缺少SMTP配置信息：{missing_str}。请通过Chat提供这些信息："
                f"1. SMTP服务器地址（如smtp.qq.com）"
                f"2. SMTP端口号（如465或587）"
                f"3. 发件人邮箱地址"
                f"4. 发件人邮箱授权码/密码"
            )

    def _load_saved_config(self) -> Optional[Dict[str, Any]]:
        """加载已保存的SMTP配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"加载保存的SMTP配置失败: {e}")
        return None

    def _save_smtp_config(self, config: Dict[str, Any]) -> None:
        """保存SMTP配置到本地文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            self.logger.warning(f"保存SMTP配置失败: {e}")

    def _merge_configs(self, provided_config: Dict[str, Any]) -> Dict[str, Any]:
        """合并提供的配置和已保存的配置"""
        merged_config = {}
        
        # 首先尝试加载已保存的配置
        saved_config = self._load_saved_config()
        if saved_config:
            merged_config.update(saved_config)
        
        # 用提供的配置覆盖
        merged_config.update(provided_config)
        
        return merged_config

    def send_mail_with_config(self, to_email: str, subject: str, body: str,
                             smtp_server: Optional[str] = None,
                             smtp_port: Optional[int] = None,
                             sender_email: Optional[str] = None,
                             sender_password: Optional[str] = None) -> Dict[str, Any]:
        """发送邮件的主要方法"""
        
        # 构建配置字典
        provided_config = {
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'sender_email': sender_email,
            'sender_password': sender_password
        }
        
        # 合并配置
        merged_config = self._merge_configs(provided_config)
        
        # 验证配置是否完整
        self._validate_smtp_config(merged_config)
        
        # 保存配置供后续使用
        self._save_smtp_config(merged_config)
        
        # 创建邮件内容
        msg = MIMEMultipart()
        msg['From'] = merged_config['sender_email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # 添加正文
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 发送邮件
        try:
            context = ssl.create_default_context()
            
            if merged_config['smtp_port'] == 465:
                # SSL连接
                with smtplib.SMTP_SSL(
                    merged_config['smtp_server'],
                    merged_config['smtp_port'],
                    context=context,
                    timeout=30
                ) as server:
                    server.login(
                        merged_config['sender_email'],
                        merged_config['sender_password']
                    )
                    server.send_message(msg)
                    
            elif merged_config['smtp_port'] in [587, 25]:
                # STARTTLS连接
                with smtplib.SMTP(
                    merged_config['smtp_server'],
                    merged_config['smtp_port'],
                    timeout=30
                ) as server:
                    server.starttls(context=context)
                    server.login(
                        merged_config['sender_email'],
                        merged_config['sender_password']
                    )
                    server.send_message(msg)
                    
            else:
                raise ToolException(f"不支持的SMTP端口: {merged_config['smtp_port']}")
                
            return {
                "success": True,
                "message": f"邮件已成功发送给 {to_email}",
                "subject": subject,
                "from": merged_config['sender_email'],
                "to": to_email
            }
            
        except smtplib.SMTPAuthenticationError as e:
            raise ToolException(f"SMTP认证失败: {e}. 请检查发件人邮箱和授权码是否正确。")
        except smtplib.SMTPException as e:
            raise ToolException(f"SMTP错误: {e}")
        except ConnectionError as e:
            raise ToolException(f"网络连接错误: {e}. 请检查SMTP服务器地址和端口是否正确。")
        except TimeoutError as e:
            raise ToolException(f"连接超时: {e}. 请检查网络连接或SMTP服务器是否可用。")
        except Exception as e:
            raise ToolException(f"发送邮件时发生未知错误: {e}")

    async def execute(self, **kwargs) -> ToolResult:
        """执行工具的主方法"""
        try:
            # 提取参数
            to_email = kwargs.get('to_email')
            subject = kwargs.get('subject')
            body = kwargs.get('body')
            smtp_server = kwargs.get('smtp_server')
            smtp_port = kwargs.get('smtp_port')
            sender_email = kwargs.get('sender_email')
            sender_password = kwargs.get('sender_password')
            
            # 验证必需参数
            if not all([to_email, subject, body]):
                raise ToolException("缺少必需参数: to_email, subject, body")
            
            # 在异步环境中同步执行邮件发送
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.send_mail_with_config,
                to_email,
                subject,
                body,
                smtp_server,
                smtp_port,
                sender_email,
                sender_password
            )
            
            return ToolResult(
                success=True,
                data=result,
                message=result.get("message", "邮件发送成功")
            )
            
        except ToolException as e:
            return ToolResult(
                success=False,
                data={},
                message=str(e),
                error_type="CONFIGURATION_ERROR"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data={},
                message=f"发送邮件失败: {str(e)}",
                error_type="EXECUTION_ERROR"
            )