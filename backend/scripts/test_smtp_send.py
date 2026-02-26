#!/usr/bin/env python3
"""
SMTP 发送测试脚本 - 诊断邮件配置与 SSL 连接问题
用法: cd backend && python3 scripts/test_smtp_send.py [收件人邮箱]
"""

import os
import sys
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 确保 backend 在 path 中
_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _backend_dir)
os.chdir(_backend_dir)
from smtp_config import get_smtp_config


def test_send(to_email: str = None):
    to_email = to_email or "test@example.com"
    server, port, user, password = get_smtp_config()
    
    print("=== SMTP 配置 ===")
    print(f"  服务器: {server}")
    print(f"  端口: {port}")
    print(f"  发件人: {user}")
    print(f"  密码: {'*' * 8} (已配置)" if password else "  (未配置)")
    print()
    
    if not all([server, user, password]):
        print("错误: 配置不完整，请先在 Mac 设置 → 邮件 中填写")
        return False
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Chow Duck SMTP 测试邮件"
    msg["From"] = user
    msg["To"] = to_email
    msg.attach(MIMEText("这是一封来自 Chow Duck 的 SMTP 测试邮件。", "plain", "utf-8"))
    
    # 测试 1: 端口 465 SMTP_SSL
    if port == 465:
        print("=== 尝试 SMTP_SSL (端口 465) ===")
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, context=context, timeout=15) as s:
                s.login(user, password)
                s.sendmail(user, [to_email], msg.as_string())
            print("✅ 发送成功！")
            return True
        except (ssl.SSLError, TimeoutError, OSError) as e:
            print(f"连接失败 ({type(e).__name__}): {e}")
            print("\n尝试备用: 端口 587 + STARTTLS（部分网络 465 被限）...")
            port = 587
        except smtplib.SMTPAuthenticationError as e:
            print(f"认证失败: {e}")
            print("提示: QQ/163 需使用「授权码」而非登录密码，请在邮箱设置中获取")
            return False
        except Exception as e:
            print(f"错误: {type(e).__name__}: {e}")
            return False
    
    # 测试 2: 端口 587 STARTTLS (QQ 支持，部分网络更通畅)
    print("=== 尝试 SMTP + STARTTLS (端口 587) ===")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(server, 587, timeout=15) as s:
            s.ehlo()
            s.starttls(context=context)
            s.ehlo()
            s.login(user, password)
            s.sendmail(user, [to_email], msg.as_string())
        print("✅ 发送成功！")
        return True
    except ssl.SSLError as e:
        print(f"SSL 错误: {e}")
        print("\n尝试: 使用较宽松的 SSL 上下文...")
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with smtplib.SMTP_SSL(server, 465, context=context, timeout=15) as s:
                s.login(user, password)
                s.sendmail(user, [to_email], msg.as_string())
            print("✅ 发送成功（使用宽松 SSL）")
            return True
        except Exception as e2:
            print(f"仍失败: {e2}")
            return False
    except smtplib.SMTPAuthenticationError as e:
        print(f"认证失败: {e}")
        return False
    except Exception as e:
        print(f"错误: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    to = sys.argv[1] if len(sys.argv) > 1 else None
    ok = test_send(to)
    sys.exit(0 if ok else 1)
