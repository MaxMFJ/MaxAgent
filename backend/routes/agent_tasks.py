"""
ACP Phase 4 — Autonomous Task API

POST   /agent/tasks           创建自主任务
GET    /agent/tasks/{task_id} 查询任务状态
POST   /agent/tasks/{task_id}/resume  恢复暂停的任务
DELETE /agent/tasks/{task_id} 取消任务
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from models.acp_models import (
    CheckpointInfo,
    TaskCallerInfo,
    TaskCreateRequest,
    TaskProgress,
    TaskResponse,
    TaskStatus,
)
from services.acp_security import (
    CapabilityTokenClaims,
    extract_token_from_header,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ACP"])

# ── 内存任务存储 ─────────────────────────────────────────────────────────────
# (TaskTracker 已在 app_state 中管理 autonomous + chat 任务，这里增加 ACP 层的元数据)

_acp_tasks: Dict[str, Dict[str, Any]] = {}


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


def _task_to_response(task_meta: Dict[str, Any]) -> TaskResponse:
    """将内部 task 元数据转换为 ACP TaskResponse。"""
    checkpoints = []
    for ckpt in task_meta.get("checkpoints", []):
        checkpoints.append(CheckpointInfo(
            id=ckpt.get("id", ""),
            step=ckpt.get("step", 0),
            timestamp=ckpt.get("timestamp", ""),
            summary=ckpt.get("summary", ""),
        ))

    progress = TaskProgress(
        steps_completed=task_meta.get("steps_completed", 0),
        steps_total_estimate=task_meta.get("steps_total_estimate"),
        current_action=task_meta.get("current_action", ""),
        last_checkpoint_id=checkpoints[-1].id if checkpoints else None,
    )

    return TaskResponse(
        task_id=task_meta["task_id"],
        status=TaskStatus(task_meta.get("status", "pending")),
        goal=task_meta.get("goal", ""),
        mode=task_meta.get("mode", "autonomous"),
        progress=progress,
        checkpoints=checkpoints,
        hitl_pending=task_meta.get("hitl_pending"),
        created_at=task_meta.get("created_at", ""),
        estimated_completion=task_meta.get("estimated_completion"),
        result=task_meta.get("result"),
    )


@router.post("/tasks")
async def create_task(
    req: TaskCreateRequest,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """创建自主执行任务。"""
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    session_id = (req.context or {}).get("session_id", f"acp-{uuid.uuid4().hex[:8]}")
    now = datetime.now(timezone.utc).isoformat()

    # 注册 ACP 任务元数据
    task_meta = {
        "task_id": task_id,
        "goal": req.goal,
        "mode": req.mode,
        "status": "pending",
        "session_id": session_id,
        "created_at": now,
        "execution_policy": req.execution_policy.model_dump(),
        "caller": req.caller.model_dump() if req.caller else None,
        "steps_completed": 0,
        "steps_total_estimate": req.execution_policy.max_steps,
        "current_action": "",
        "checkpoints": [],
        "hitl_pending": None,
        "result": None,
        "estimated_completion": None,
        "asyncio_task": None,
        "stream_events": [],  # 存放流式事件供 SSE 读取
    }
    _acp_tasks[task_id] = task_meta

    # 启动后台执行
    bg_task = asyncio.create_task(
        _run_autonomous_task(task_id, req, session_id)
    )
    task_meta["asyncio_task"] = bg_task
    task_meta["status"] = "running"

    return _task_to_response(task_meta)


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: str,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """查询任务状态。"""
    # 先查 ACP 任务存储
    meta = _acp_tasks.get(task_id)
    if meta:
        return _task_to_response(meta)

    # 回退到 app_state TaskTracker
    try:
        from app_state import task_tracker
        tracked = await task_tracker.get(task_id)
        if tracked:
            status_map = {
                "running": TaskStatus.RUNNING,
                "completed": TaskStatus.COMPLETED,
                "error": TaskStatus.FAILED,
                "stopped": TaskStatus.CANCELLED,
            }
            return TaskResponse(
                task_id=tracked.task_id,
                status=status_map.get(tracked.status.value, TaskStatus.RUNNING),
                goal=tracked.task_description,
                created_at=datetime.fromtimestamp(
                    tracked.created_at, tz=timezone.utc
                ).isoformat(),
            )
    except Exception:
        pass

    # 回退到 invoke async task store
    from routes.agent_invoke import get_async_task_result
    async_result = get_async_task_result(task_id)
    if async_result:
        status_map = {
            "running": TaskStatus.RUNNING,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
        }
        return TaskResponse(
            task_id=task_id,
            status=status_map.get(async_result["status"], TaskStatus.RUNNING),
            goal="(async invoke task)",
            result=async_result.get("result"),
        )

    raise HTTPException(404, f"Task not found: {task_id}")


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """列出所有 ACP 任务。"""
    tasks = []
    for meta in _acp_tasks.values():
        if status and meta.get("status") != status:
            continue
        tasks.append(_task_to_response(meta))
        if len(tasks) >= limit:
            break
    return {"tasks": tasks, "total": len(tasks)}


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """恢复暂停或失败的任务。"""
    meta = _acp_tasks.get(task_id)
    if not meta:
        raise HTTPException(404, f"Task not found: {task_id}")
    if meta["status"] not in ("paused", "failed"):
        raise HTTPException(
            409, f"Task cannot be resumed (status={meta['status']})"
        )

    # 尝试从 checkpoint 恢复
    try:
        from task_persistence import get_persistence_manager
        pm = get_persistence_manager()
        checkpoint = await pm.load_checkpoint(task_id)
        if checkpoint:
            meta["status"] = "running"
            bg_task = asyncio.create_task(
                _resume_from_checkpoint(task_id, checkpoint)
            )
            meta["asyncio_task"] = bg_task
            return _task_to_response(meta)
    except Exception as e:
        logger.warning("Checkpoint resume failed: %s", e)

    meta["status"] = "running"
    return _task_to_response(meta)


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """取消任务。"""
    meta = _acp_tasks.get(task_id)
    if not meta:
        raise HTTPException(404, f"Task not found: {task_id}")

    if meta["status"] in ("completed", "cancelled"):
        return {"task_id": task_id, "status": meta["status"], "message": "Already terminated"}

    # 取消 asyncio 任务
    bg_task = meta.get("asyncio_task")
    if bg_task and not bg_task.done():
        bg_task.cancel()

    meta["status"] = "cancelled"
    meta["result"] = {"reason": "Cancelled by API request"}

    # 追加取消事件到流
    _append_stream_event(task_id, {
        "type": "cancelled",
        "message": "Task cancelled",
    })

    return _task_to_response(meta)


# ── 后台自主执行 ─────────────────────────────────────────────────────────────

async def _run_autonomous_task(
    task_id: str,
    req: TaskCreateRequest,
    session_id: str,
):
    """后台运行自主任务，更新元数据和流式事件。"""
    meta = _acp_tasks.get(task_id)
    if not meta:
        return

    try:
        from app_state import get_autonomous_agent
        agent = get_autonomous_agent()
        if not agent:
            meta["status"] = "failed"
            meta["result"] = {"error": "Autonomous agent not initialized"}
            return

        _append_stream_event(task_id, {
            "type": "progress",
            "message": f"Starting autonomous task: {req.goal}",
        })

        # 调用 autonomous agent
        step = 0
        async for chunk in agent.run(req.goal, session_id=session_id):
            if not isinstance(chunk, dict):
                continue

            step += 1
            meta["steps_completed"] = step
            meta["current_action"] = chunk.get("type", "")

            # 追加事件到流
            _append_stream_event(task_id, chunk)

            chunk_type = chunk.get("type", "")
            if chunk_type in ("done", "task_complete"):
                meta["status"] = "completed"
                meta["result"] = chunk.get("result", chunk)
                break
            elif chunk_type == "error":
                policy = req.execution_policy
                if policy.on_failure == "pause":
                    meta["status"] = "paused"
                elif policy.on_failure == "abort":
                    meta["status"] = "failed"
                meta["result"] = {"error": chunk.get("error", str(chunk))}
                break

            # Checkpoint
            if (
                req.execution_policy.auto_checkpoint
                and step % req.execution_policy.checkpoint_interval_steps == 0
            ):
                ckpt_id = f"ckpt-{step:04d}"
                meta["checkpoints"].append({
                    "id": ckpt_id,
                    "step": step,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": f"Step {step}: {chunk.get('type', 'action')}",
                })
                _append_stream_event(task_id, {
                    "type": "checkpoint",
                    "checkpoint_id": ckpt_id,
                    "step": step,
                })

        # 未显式完成则标记完成
        if meta["status"] == "running":
            meta["status"] = "completed"

    except asyncio.CancelledError:
        meta["status"] = "cancelled"
    except Exception as e:
        logger.error("ACP task %s failed: %s", task_id, e, exc_info=True)
        meta["status"] = "failed"
        meta["result"] = {"error": str(e)}
        _append_stream_event(task_id, {"type": "error", "error": str(e)})


async def _resume_from_checkpoint(task_id: str, checkpoint):
    """从 checkpoint 恢复任务（占位实现）。"""
    meta = _acp_tasks.get(task_id)
    if meta:
        meta["status"] = "completed"
        meta["result"] = {"message": "Resumed from checkpoint (placeholder)"}


def _append_stream_event(task_id: str, event: Dict[str, Any]):
    """追加事件到任务的流式事件缓冲。"""
    meta = _acp_tasks.get(task_id)
    if meta:
        events = meta.setdefault("stream_events", [])
        events.append(event)
        # 限制最大缓冲量
        if len(events) > 1000:
            events[:] = events[-500:]


def get_task_stream_events(task_id: str) -> Optional[List[Dict[str, Any]]]:
    """获取任务的流式事件（供 SSE 路由使用）。"""
    meta = _acp_tasks.get(task_id)
    if not meta:
        return None
    return meta.get("stream_events", [])


def get_task_status(task_id: str) -> Optional[str]:
    """获取任务状态。"""
    meta = _acp_tasks.get(task_id)
    if meta:
        return meta.get("status")
    return None
