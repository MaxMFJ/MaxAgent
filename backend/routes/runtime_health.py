"""
Runtime Health API — /runtime/* endpoints (v3.0 Final)

Endpoints:
  GET /runtime/health          — Health snapshot with readiness levels
  GET /runtime/task/{task_id}  — Task explain (single task deep-dive)
  GET /runtime/queues          — Queue state overview
  GET /runtime/workers         — Worker diagnostics
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/health")
async def runtime_health():
    """Health snapshot with readiness levels (OK / DEGRADED / CRITICAL)"""
    from services.runtime_health import get_runtime_health
    return get_runtime_health()


@router.get("/task/{task_id}")
async def task_explain(task_id: str):
    """Deep-dive into a single task: status, timings, retries, journal events"""
    from services.runtime_health import get_task_explain
    result = get_task_explain(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return result


@router.get("/queues")
async def queue_state():
    """Queue state: per-type sizes, overflow, pressure, active pull loops"""
    from services.runtime_health import get_queue_state
    return get_queue_state()


@router.get("/workers")
async def worker_diagnostics():
    """Worker diagnostics: per-duck health, lease, assignment, status"""
    from services.runtime_health import get_worker_diagnostics
    return get_worker_diagnostics()
