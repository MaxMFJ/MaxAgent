"""
ACP Phase 8 — Auth Token Routes

POST /agent/auth/token   生成 capability token
GET  /agent/auth/scopes  列出可用权限范围
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from models.acp_models import TokenTier
from services.acp_security import CapabilityTokenFactory, verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent/auth", tags=["ACP"])


class TokenRequest(BaseModel):
    agent_id: str
    tier: int = 1  # 0=public, 1=session, 2=capability, 3=admin
    allowed_tools: list = []
    denied_tools: list = []
    allowed_modes: list = ["chat", "autonomous"]
    ttl_s: int = 3600
    max_cost_usd: float = 1.0


class DelegateRequest(BaseModel):
    parent_token: str
    new_agent_id: str
    allowed_tools: Optional[list] = None
    allowed_modes: Optional[list] = None
    ttl_s: int = 600


@router.post("/token")
async def create_token(req: TokenRequest):
    """
    生成 capability token。
    生产环境中应增加管理员认证。
    """
    try:
        tier = TokenTier(req.tier)
    except ValueError:
        raise HTTPException(400, f"Invalid tier: {req.tier} (allowed: 0-3)")

    # Admin token 需要强认证（此处仅占位 — 由部署层保护）
    if tier == TokenTier.ADMIN:
        logger.warning("Admin token requested for agent_id=%s", req.agent_id)

    token = CapabilityTokenFactory.create(
        subject=req.agent_id,
        tier=tier,
        allowed_tools=req.allowed_tools or None,
        denied_tools=req.denied_tools or None,
        allowed_modes=req.allowed_modes or None,
        ttl_s=req.ttl_s,
        max_cost_usd=req.max_cost_usd,
    )
    return {"token": token, "tier": tier.value, "ttl_s": req.ttl_s}


@router.post("/delegate")
async def delegate_token(req: DelegateRequest):
    """
    委托令牌：从父令牌派生范围更小的子令牌。
    新令牌范围 = 父令牌范围 ∩ requested_scope。
    """
    child_token = CapabilityTokenFactory.delegate(
        parent_token=req.parent_token,
        new_subject=req.new_agent_id,
        requested_allowed_tools=req.allowed_tools,
        requested_modes=req.allowed_modes,
        ttl_s=req.ttl_s,
    )
    if not child_token:
        raise HTTPException(401, "Parent token is invalid or expired")

    return {"token": child_token, "delegated_from": req.new_agent_id}


@router.get("/scopes")
async def list_scopes():
    """列出可用的权限范围信息。"""
    # 获取当前可用工具名称
    tools = []
    try:
        from app_state import get_agent_core
        core = get_agent_core()
        if core:
            tools = [t.name for t in core.registry.list_tools()]
    except Exception:
        pass

    return {
        "tiers": {
            0: {"name": "public", "description": "Read-only access to manifest and capabilities"},
            1: {"name": "session", "description": "Basic invocation (chat, read-only tools)"},
            2: {"name": "capability", "description": "Scoped tool access with negotiated contract"},
            3: {"name": "admin", "description": "Full access including config and duck management"},
        },
        "available_tools": sorted(tools),
        "available_modes": ["chat", "autonomous", "dag", "capsule"],
    }
