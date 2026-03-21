"""
ACP Security — Capability Token 生成与校验

Phase 8: 分层信任模型
- Layer 0: Public (无需鉴权)
- Layer 1: Session Token (基础调用)
- Layer 2: Capability Token (范围限定)
- Layer 3: Admin Token (管理操作)

使用 HMAC-SHA256 签名 (轻量级 JWT 替代), 私钥不离开 MacAgent 实例。
"""
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Dict, List, Optional, Set

from models.acp_models import (
    CapabilityTokenClaims,
    ContractInfo,
    TokenScope,
    TokenTier,
)

logger = logging.getLogger(__name__)

# ── 密钥管理 ─────────────────────────────────────────────────────────────────

_SECRET_KEY: Optional[str] = None


def _get_secret_key() -> str:
    """获取或生成 HMAC 签名密钥，优先从环境变量读取。"""
    global _SECRET_KEY
    if _SECRET_KEY:
        return _SECRET_KEY
    _SECRET_KEY = os.environ.get("ACP_TOKEN_SECRET")
    if not _SECRET_KEY:
        _SECRET_KEY = secrets.token_hex(32)
        logger.info("ACP token secret auto-generated (set ACP_TOKEN_SECRET for persistence)")
    return _SECRET_KEY


# ── Token 编解码 ─────────────────────────────────────────────────────────────

def _sign(payload_bytes: bytes) -> str:
    """HMAC-SHA256 签名"""
    return hmac.new(
        _get_secret_key().encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


def create_token(claims: CapabilityTokenClaims) -> str:
    """
    生成 capability token (payload.signature 格式)。
    """
    import base64

    payload_json = claims.model_dump_json()
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    sig = _sign(payload_json.encode())
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> Optional[CapabilityTokenClaims]:
    """
    验证 token。成功返回 claims，失败返回 None。
    检查：签名 + 过期时间。
    """
    import base64

    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
    except Exception:
        return None
    expected_sig = _sign(payload_json.encode())
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        claims = CapabilityTokenClaims.model_validate_json(payload_json)
    except Exception:
        return None
    # 过期检查
    if claims.exp > 0 and time.time() > claims.exp:
        return None
    return claims


# ── Token 工厂 ───────────────────────────────────────────────────────────────

class CapabilityTokenFactory:
    """生成和管理 capability token 的工厂。"""

    @staticmethod
    def create(
        subject: str,
        tier: TokenTier = TokenTier.SESSION,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None,
        allowed_modes: Optional[List[str]] = None,
        ttl_s: int = 3600,
        hitl_bypass: bool = False,
        max_cost_usd: float = 1.0,
        max_task_duration_s: int = 600,
        delegation_chain: Optional[List[str]] = None,
    ) -> str:
        now = time.time()
        scope = TokenScope(
            tier=tier,
            allowed_tools=allowed_tools or [],
            denied_tools=denied_tools or [],
            allowed_modes=allowed_modes or ["chat", "autonomous"],
            max_task_duration_s=max_task_duration_s,
            hitl_bypass=hitl_bypass,
            max_cost_usd=max_cost_usd,
        )
        claims = CapabilityTokenClaims(
            sub=subject,
            iat=now,
            exp=now + ttl_s,
            scope=scope,
            delegation_chain=delegation_chain or [],
        )
        return create_token(claims)

    @staticmethod
    def delegate(
        parent_token: str,
        new_subject: str,
        requested_allowed_tools: Optional[List[str]] = None,
        requested_modes: Optional[List[str]] = None,
        ttl_s: int = 600,
    ) -> Optional[str]:
        """
        委托令牌：新令牌范围 = 父令牌范围 ∩ requested_scope。
        只能收窄权限，不能扩展。
        """
        parent = verify_token(parent_token)
        if not parent:
            return None

        parent_allowed = set(parent.scope.allowed_tools) if parent.scope.allowed_tools else None
        parent_denied = set(parent.scope.denied_tools)
        parent_modes = set(parent.scope.allowed_modes)

        # 交叉计算
        if requested_allowed_tools is not None:
            if parent_allowed is not None:
                new_allowed = list(set(requested_allowed_tools) & parent_allowed)
            else:
                new_allowed = requested_allowed_tools
        else:
            new_allowed = list(parent_allowed) if parent_allowed else []

        new_modes = list(
            set(requested_modes or parent_modes) & parent_modes
        )

        # 新 tier 不能超过父级
        new_tier = min(parent.scope.tier, TokenTier.CAPABILITY)

        chain = list(parent.delegation_chain) + [new_subject]

        return CapabilityTokenFactory.create(
            subject=new_subject,
            tier=new_tier,
            allowed_tools=new_allowed,
            denied_tools=list(parent_denied),
            allowed_modes=new_modes,
            ttl_s=min(ttl_s, int(parent.exp - time.time())) if parent.exp > 0 else ttl_s,
            hitl_bypass=False,  # 委托令牌不能绕过 HITL
            max_cost_usd=parent.scope.max_cost_usd,
            max_task_duration_s=min(
                parent.scope.max_task_duration_s, 600
            ),
            delegation_chain=chain,
        )

    @staticmethod
    def create_contract(
        subject: str,
        allowed_tools: List[str],
        denied_tools: List[str],
        ttl_s: int = 600,
    ) -> ContractInfo:
        """协商后创建合约 token（Phase 6 使用）。"""
        from datetime import datetime, timezone

        token = CapabilityTokenFactory.create(
            subject=subject,
            tier=TokenTier.CAPABILITY,
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
            ttl_s=ttl_s,
        )
        expires_at = datetime.fromtimestamp(
            time.time() + ttl_s, tz=timezone.utc
        ).isoformat()
        return ContractInfo(
            token=token,
            expires_at=expires_at,
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
        )


# ── Token 验证中间件 ─────────────────────────────────────────────────────────

def extract_token_from_header(authorization: Optional[str]) -> Optional[str]:
    """从 Authorization: Bearer <token> 中提取 token。"""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def check_tool_permission(
    claims: CapabilityTokenClaims, tool_id: str
) -> bool:
    """检查 token 是否允许调用指定工具。"""
    if claims.scope.denied_tools and tool_id in claims.scope.denied_tools:
        return False
    if claims.scope.allowed_tools:
        return tool_id in claims.scope.allowed_tools
    return True  # 空白名单 = 允许全部（只要不在黑名单中）
