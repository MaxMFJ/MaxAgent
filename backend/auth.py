"""
认证模块
Token 生成、验证、认证状态管理。
"""
import os
import secrets
from typing import Optional

AUTH_TOKEN: Optional[str] = os.environ.get("MACAGENT_AUTH_TOKEN")
AUTH_ENABLED: bool = os.environ.get("MACAGENT_AUTH_ENABLED", "false").lower() == "true"


def generate_auth_token() -> str:
    return secrets.token_urlsafe(32)


def verify_token(token: Optional[str]) -> bool:
    if not AUTH_ENABLED:
        return True
    if not AUTH_TOKEN:
        return True
    return token == AUTH_TOKEN


def set_auth(enabled: bool, token: Optional[str] = None):
    global AUTH_ENABLED, AUTH_TOKEN
    AUTH_ENABLED = enabled
    if token is not None:
        AUTH_TOKEN = token
