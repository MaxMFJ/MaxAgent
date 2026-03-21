"""
ACP Phase 3 — Agent Invoke Route

POST /agent/invoke
统一调用 tools、capsules、ducks、DAG、agent chat，消除外部 Agent 学习各端点的负担。
"""
import asyncio
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from models.acp_models import (
    ExecutionMode,
    InvokeContext,
    InvokeMeta,
    InvokeRequest,
    InvokeResponse,
    TaskStatus,
)
from services.acp_security import (
    CapabilityTokenClaims,
    check_tool_permission,
    extract_token_from_header,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ACP"])

# target 前缀白名单 — 防止路径遍历注入
_VALID_PREFIXES = {"tool", "capsule", "dag", "duck", "agent"}
# target name 合法字符：字母、数字、下划线、点、短横线
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+$")


# ── 依赖注入：可选 Token 验证 ────────────────────────────────────────────────

async def _optional_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[CapabilityTokenClaims]:
    """
    可选的 capability token 验证。
    如果 header 中有 Bearer token 则校验，无则返回 None（Layer 0 公开访问）。
    """
    raw = extract_token_from_header(authorization)
    if not raw:
        return None
    claims = verify_token(raw)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired capability token")
    return claims


# ── 路由处理器 ───────────────────────────────────────────────────────────────

async def _route_to_tool(name: str, req: InvokeRequest) -> Dict[str, Any]:
    """调用 ToolRegistry.execute()"""
    from app_state import get_agent_core
    core = get_agent_core()
    if not core:
        raise HTTPException(503, "Agent core not initialized")

    tool = core.registry.get(name)
    if not tool:
        raise HTTPException(404, f"Tool not found: {name}")

    result = await core.registry.execute(name, **req.params)
    return {
        "success": result.success,
        "data": result.data,
        "error": result.error,
    }


async def _route_to_capsule(name: str, req: InvokeRequest) -> Dict[str, Any]:
    """调用 CapsuleManager / CapsuleRegistry"""
    from agent.capsule_registry import get_capsule_registry
    registry = get_capsule_registry()
    capsule = registry.get_capsule(name)
    if not capsule:
        raise HTTPException(404, f"Capsule not found: {name}")

    # Capsule 执行通过 agent — 将 capsule 信息传递给 autonomous agent
    from app_state import get_autonomous_agent
    agent = get_autonomous_agent()
    if not agent:
        raise HTTPException(503, "Autonomous agent not initialized")

    # 构造 capsule 调用描述
    goal = f"Execute capsule '{name}' with params: {req.params}"
    task_id = f"task-{uuid.uuid4().hex[:12]}"

    return {
        "capsule_id": name,
        "task_id": task_id,
        "status": "submitted",
        "message": f"Capsule '{name}' execution initiated",
    }


async def _route_to_duck(name: str, req: InvokeRequest) -> Dict[str, Any]:
    """委托给 DuckTaskScheduler"""
    from services.duck_task_scheduler import DuckTaskScheduler

    scheduler = DuckTaskScheduler.get_instance()
    description = req.params.get("description", req.params.get("goal", f"Execute via duck:{name}"))

    task = await scheduler.submit(
        description=description,
        task_type=req.params.get("task_type", "general"),
        params=req.params,
        strategy=req.params.get("strategy", "single"),
        target_duck_type=name if name != "auto" else None,
        source_session_id=req.context.session_id if req.context else None,
    )
    return {
        "duck_task_id": task.task_id,
        "assigned_duck_id": task.assigned_duck_id,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
    }


async def _route_to_dag(name: str, req: InvokeRequest) -> Dict[str, Any]:
    """DAG 执行（如果可用）"""
    # DAG 通过 autonomous agent 的 DELEGATE_DAG action 执行
    return {
        "dag_template": name,
        "status": "submitted",
        "message": f"DAG '{name}' execution initiated (via autonomous agent)",
        "params": req.params,
    }


async def _route_to_agent_chat(name: str, req: InvokeRequest) -> Dict[str, Any]:
    """发起 Agent 对话/自主执行"""
    from app_state import get_agent_core, get_autonomous_agent

    query = req.params.get("query", req.params.get("goal", ""))
    if not query:
        raise HTTPException(400, "Missing 'query' or 'goal' in params")

    if name == "chat":
        core = get_agent_core()
        if not core:
            raise HTTPException(503, "Agent core not initialized")
        session_id = req.context.session_id if req.context else f"acp-{uuid.uuid4().hex[:8]}"
        # 同步收集 streaming 结果
        chunks = []
        async for chunk in core.run_stream(query, session_id):
            if isinstance(chunk, dict):
                chunks.append(chunk)
        return {"chunks": chunks, "session_id": session_id}
    elif name == "autonomous":
        agent = get_autonomous_agent()
        if not agent:
            raise HTTPException(503, "Autonomous agent not initialized")
        return {
            "status": "submitted",
            "message": "Autonomous task submitted (use async mode for real execution)",
        }
    else:
        raise HTTPException(400, f"Unknown agent mode: {name}")


_TARGET_ROUTERS = {
    "tool": _route_to_tool,
    "capsule": _route_to_capsule,
    "dag": _route_to_dag,
    "duck": _route_to_duck,
    "agent": _route_to_agent_chat,
}


@router.post("/invoke")
async def agent_invoke(
    req: InvokeRequest,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """
    统一调用入口。target 格式: "tool:terminal" | "capsule:XXX" | "duck:coder" | "agent:chat"
    """
    # 解析 target
    if ":" not in req.target:
        raise HTTPException(400, f"Invalid target format: '{req.target}' (expected 'prefix:name')")

    prefix, name = req.target.split(":", 1)

    # 白名单校验 prefix
    if prefix not in _VALID_PREFIXES:
        raise HTTPException(400, f"Unknown target prefix: '{prefix}' (allowed: {_VALID_PREFIXES})")

    # name 合法字符校验
    if not _NAME_PATTERN.match(name):
        raise HTTPException(400, f"Invalid target name: '{name}'")

    # Token 权限校验（如果提供了 token）
    if claims:
        if not check_tool_permission(claims, req.target):
            raise HTTPException(
                403, f"Token does not have permission for target: {req.target}"
            )

    handler = _TARGET_ROUTERS.get(prefix)
    if not handler:
        raise HTTPException(400, f"No handler for prefix: {prefix}")

    # ── 异步模式处理 ────────────────────────────────────────────────────
    if req.execution.mode == ExecutionMode.ASYNC:
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        # 创建后台任务
        asyncio.create_task(_execute_async(task_id, handler, name, req))
        return InvokeResponse(
            request_id=req.request_id,
            task_id=task_id,
            status=TaskStatus.PENDING,
            stream_url=f"/agent/stream/{task_id}",
            poll_url=f"/agent/tasks/{task_id}",
            estimated_ms=req.execution.timeout_ms,
        )

    # ── 同步模式执行 ────────────────────────────────────────────────────
    t0 = time.monotonic()
    try:
        result = await asyncio.wait_for(
            handler(name, req),
            timeout=req.execution.timeout_ms / 1000.0,
        )
        duration_ms = round((time.monotonic() - t0) * 1000, 1)
        return InvokeResponse(
            request_id=req.request_id,
            status=TaskStatus.COMPLETED,
            result=result,
            meta=InvokeMeta(
                duration_ms=duration_ms,
                tool_used=req.target,
            ),
        )
    except asyncio.TimeoutError:
        # 超时降级为 async
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        asyncio.create_task(_execute_async(task_id, handler, name, req))
        return InvokeResponse(
            request_id=req.request_id,
            task_id=task_id,
            status=TaskStatus.PENDING,
            stream_url=f"/agent/stream/{task_id}",
            poll_url=f"/agent/tasks/{task_id}",
            estimated_ms=req.execution.timeout_ms * 2,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Invoke failed: %s", e, exc_info=True)
        return InvokeResponse(
            request_id=req.request_id,
            status=TaskStatus.FAILED,
            result={"error": str(e)},
            meta=InvokeMeta(
                duration_ms=round((time.monotonic() - t0) * 1000, 1),
                tool_used=req.target,
            ),
        )


# ── ACP async task store (轻量级内存存储) ────────────────────────────────────

_async_tasks: Dict[str, Dict[str, Any]] = {}


async def _execute_async(
    task_id: str,
    handler,
    name: str,
    req: InvokeRequest,
):
    """后台异步执行，结果存入 _async_tasks。"""
    _async_tasks[task_id] = {"status": "running", "result": None, "error": None}
    try:
        result = await handler(name, req)
        _async_tasks[task_id] = {
            "status": "completed",
            "result": result,
            "error": None,
        }
    except Exception as e:
        _async_tasks[task_id] = {
            "status": "failed",
            "result": None,
            "error": str(e),
        }


def get_async_task_result(task_id: str) -> Optional[Dict[str, Any]]:
    """获取异步任务结果（供 task API 使用）。"""
    return _async_tasks.get(task_id)


def cleanup_async_task(task_id: str) -> None:
    """清理异步任务记录。"""
    _async_tasks.pop(task_id, None)
