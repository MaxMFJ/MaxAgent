"""
ACP Phase 1 — Agent Manifest Route

GET /.well-known/agent.json
向外部 Agent 提供单一、零歧义的能力声明。运行时动态生成，不缓存。
"""
import logging
from fastapi import APIRouter

from models.acp_models import (
    AgentInfo,
    AgentManifest,
    AuthBlock,
    CapabilityBlock,
    DelegationConfig,
    LimitsBlock,
    MetadataBlock,
    ProtocolBlock,
    StreamingConfig,
    SubagentConfig,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ACP"])


def _build_capabilities() -> CapabilityBlock:
    """从 app_state 动态读取当前能力。"""
    from app_state import (
        ENABLE_HITL,
        ENABLE_SESSION_RESUME,
        SUBAGENT_MAX_CONCURRENT,
    )

    duck_types = ["general"]
    try:
        from services.duck_registry import DuckRegistry
        registry = DuckRegistry.get_instance()
        # 同步读取已知 duck 类型（不 await）
        from services.duck_protocol import DuckType
        duck_types = [dt.value.lower() for dt in DuckType]
    except Exception:
        pass

    modes = ["chat", "autonomous"]
    try:
        from agent.capsule_registry import get_capsule_registry
        if get_capsule_registry().list_capsules():
            modes.append("capsule")
    except Exception:
        pass
    # DAG 模式始终声明（架构支持）
    modes.append("dag")

    return CapabilityBlock(
        modes=modes,
        autonomous=True,
        delegation=DelegationConfig(
            strategies=["direct", "single", "multi"],
            duck_types=duck_types,
        ),
        hitl=ENABLE_HITL,
        session_resume=ENABLE_SESSION_RESUME,
        subagents=SubagentConfig(max_concurrent=SUBAGENT_MAX_CONCURRENT),
        streaming=StreamingConfig(sse=True, websocket=True),
    )


def _build_auth() -> AuthBlock:
    """根据当前认证配置生成 auth 块。"""
    from auth import AUTH_ENABLED
    methods = ["none"]
    if AUTH_ENABLED:
        methods.append("bearer")
    methods.append("capability_token")
    return AuthBlock(methods=methods)


@router.get("/.well-known/agent.json", include_in_schema=False)
async def agent_manifest():
    """
    Agent Manifest — 自描述入口。
    外部 Agent 访问此 URL 即可完整理解 MacAgent 的所有能力。
    """
    agent = AgentInfo()
    try:
        from app_state import get_llm_client
        llm = get_llm_client()
        if llm:
            agent.version = "3.5.0"
    except Exception:
        pass

    return AgentManifest(
        agent=agent,
        capabilities=_build_capabilities(),
        auth=_build_auth(),
    )
