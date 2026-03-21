"""
ACP Phase 6 — Capability Negotiation

POST /agent/negotiate
两个 Agent 在任务委托前交换能力声明，避免不兼容的任务分配。
一次往返完成协商。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from models.acp_models import (
    ContractInfo,
    ExecutionPlan,
    NegotiateRequest,
    NegotiateResponse,
)
from services.acp_security import (
    CapabilityTokenClaims,
    CapabilityTokenFactory,
    extract_token_from_header,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ACP"])


async def _optional_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[CapabilityTokenClaims]:
    raw = extract_token_from_header(authorization)
    if not raw:
        return None
    claims = verify_token(raw)
    if not claims:
        raise HTTPException(401, "Invalid or expired token")
    return claims


@router.post("/negotiate")
async def negotiate(
    req: NegotiateRequest,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """
    能力协商端点。
    返回匹配能力、执行建议和合约 token。
    """
    # 获取本地可用能力
    available_tools: set = set()
    try:
        from app_state import get_agent_core
        core = get_agent_core()
        if core:
            available_tools = {t.name for t in core.registry.list_tools()}
    except Exception:
        pass

    # 检查 required capabilities
    required = set(req.negotiation.required_capabilities)
    optional = set(req.negotiation.optional_capabilities)
    missing = required - available_tools

    if missing:
        return NegotiateResponse(
            accepted=False,
            matched_capabilities=list(required & available_tools),
            unavailable=list(missing),
            reason=f"Missing required capabilities: {', '.join(sorted(missing))}",
        )

    matched = list(required | (optional & available_tools))
    warnings = []
    denied_from_constraints = []

    # 处理约束
    if req.task_hint and req.task_hint.constraints:
        for constraint in req.task_hint.constraints:
            if constraint == "no_external_api_calls":
                denied_from_constraints.extend(["network", "http", "fetch"])
                if "network" in available_tools:
                    warnings.append("network capability available but excluded per constraint")

    # 查询 duck 可用性
    available_ducks = 0
    recommended_target = ""
    if req.task_hint and req.task_hint.preferred_duck:
        try:
            from services.duck_registry import DuckRegistry
            registry = DuckRegistry.get_instance()
            ducks = await registry.list_available()
            available_ducks = len(ducks)
            recommended_target = f"duck:{req.task_hint.preferred_duck}"
        except Exception:
            recommended_target = "agent:autonomous"
    else:
        recommended_target = "agent:autonomous"

    # 生成合约 token
    allowed_tools = list(
        (
            set(matched) - set(denied_from_constraints)
        )
    )
    contract = CapabilityTokenFactory.create_contract(
        subject=req.proposer.agent_id,
        allowed_tools=allowed_tools,
        denied_tools=denied_from_constraints,
        ttl_s=req.negotiation.timeout_s,
    )

    execution_plan = ExecutionPlan(
        recommended_target=recommended_target,
        available_ducks=available_ducks,
        estimated_duration_s=req.negotiation.timeout_s // 2,
        estimated_cost_usd=0.0,
        mode="async" if req.task_hint and req.task_hint.estimated_steps > 10 else "sync",
    )

    return NegotiateResponse(
        accepted=True,
        matched_capabilities=matched,
        unavailable=[],
        execution_plan=execution_plan,
        contract=contract,
        warnings=warnings,
    )
