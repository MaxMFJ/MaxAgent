#!/usr/bin/env python3
"""ACP 模块快速验证脚本"""
import sys

def main():
    # 1. 模型导入
    from models.acp_models import (
        AgentManifest, CapabilityGraph, InvokeRequest, InvokeResponse,
        TaskCreateRequest, TaskResponse, ACPEvent, NegotiateRequest, NegotiateResponse,
        CapabilityTokenClaims
    )
    print("OK models/acp_models.py")

    # 2. 安全模块
    from services.acp_security import (
        CapabilityTokenFactory, create_token, verify_token, check_tool_permission
    )
    print("OK services/acp_security.py")

    # 3. 流式适配器
    from services.acp_streaming import StreamingAdapter
    print("OK services/acp_streaming.py")

    # 4. Token 创建和验证
    token = CapabilityTokenFactory.create(
        subject="test-agent",
        tier=1,
        allowed_tools=["terminal", "file"],
        ttl_s=60,
    )
    print(f"   Token created: {token[:40]}...")
    claims = verify_token(token)
    assert claims is not None, "Token verification failed"
    print(f"   Token verified: sub={claims.sub}, allowed={claims.scope.allowed_tools}")

    # 5. 委托令牌
    child = CapabilityTokenFactory.delegate(token, "child-agent", ["terminal"], ttl_s=30)
    assert child is not None, "Delegation failed"
    child_claims = verify_token(child)
    assert child_claims is not None, "Child token verification failed"
    print(f"   Delegated: sub={child_claims.sub}, allowed={child_claims.scope.allowed_tools}, chain={child_claims.delegation_chain}")

    # 6. 权限校验
    assert check_tool_permission(claims, "terminal") == True
    assert check_tool_permission(claims, "docker") == False
    print("OK permission check")

    # 7. 流式适配器
    from models.acp_models import Visibility
    adapter = StreamingAdapter(task_id="test-123", visibility=Visibility.STANDARD)
    event = adapter.adapt({"type": "action", "tool": "terminal", "command": "ls"})
    assert event is not None
    print(f"   Stream event: {event.event}, seq={event.seq}")
    sse = adapter.format_sse(event)
    assert "event: agent.action" in sse
    print("OK streaming adapter")

    # 8. Manifest 模型
    manifest = AgentManifest()
    d = manifest.model_dump()
    assert d["acp_version"] == "1.0"
    assert "invocation" in d["protocols"]
    print("OK manifest model")

    # 9. Invoke 模型
    req = InvokeRequest(target="tool:terminal", params={"command": "ls"})
    assert req.target == "tool:terminal"
    print("OK invoke model")

    # 10. Route imports (不需要 FastAPI 运行)
    from routes.agent_manifest import router as r1
    from routes.agent_capability import router as r2
    from routes.agent_invoke import router as r3
    from routes.agent_tasks import router as r4
    from routes.agent_stream import router as r5
    from routes.agent_negotiate import router as r6
    from routes.agent_auth import router as r7
    print("OK all route imports")

    print("\n=== All 10 checks passed ===")

if __name__ == "__main__":
    main()
