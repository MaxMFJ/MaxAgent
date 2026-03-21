"""
Remote Pull Protocol — Duck Runtime v3.0

Allows remote worker nodes (RWN) to pull tasks from the
Runtime Authority Node (RAN) via HTTP.

Core logic for:
- Worker registration (reuses DuckRegistry)
- Task pull from ready_queues
- Heartbeat / lease renewal
- Task completion (delegates to scheduler)
- Bearer token auth

Architecture: pull-based, single authority, distributed execution.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from services.duck_protocol import (
    DuckInfo,
    DuckStatus,
    DuckType,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────
DEFAULT_LEASE_SECONDS = 30
WORKER_TOKEN = os.environ.get("DUCK_WORKER_TOKEN", "")


# ─── Auth ────────────────────────────────────────────

def validate_worker_token(token: str) -> bool:
    """Validate bearer token against env var DUCK_WORKER_TOKEN"""
    if not WORKER_TOKEN:
        # No token configured → allow all (dev mode)
        return True
    return token == WORKER_TOKEN


# ─── Worker Registration ────────────────────────────

async def register_worker(
    worker_id: str,
    duck_type: str,
    capabilities: list = None,
    version: str = "1.0",
) -> Dict[str, Any]:
    """
    Register a remote worker. Reuses DuckRegistry internally.
    Returns lease_seconds.
    """
    from services.duck_registry import DuckRegistry

    # Validate duck_type
    try:
        dtype = DuckType(duck_type)
    except ValueError:
        valid = [t.value for t in DuckType]
        raise ValueError(f"Invalid duck_type '{duck_type}'. Valid: {valid}")

    registry = DuckRegistry.get_instance()
    await registry.initialize()

    info = DuckInfo(
        duck_id=worker_id,
        name=worker_id,
        duck_type=dtype,
        skills=capabilities or [],
        is_local=False,  # remote worker
    )

    await registry.register(info)

    # Track remote metrics
    try:
        from services.runtime_metrics import metrics
        metrics.record_remote_worker_register(worker_id)
    except Exception:
        pass

    logger.info(
        f"[remote_pull] Worker registered: {worker_id} type={duck_type} "
        f"version={version}"
    )

    return {
        "worker_id": worker_id,
        "lease_seconds": DEFAULT_LEASE_SECONDS,
        "status": "registered",
    }


# ─── Pull Task ──────────────────────────────────────

async def pull_task(
    worker_id: str,
    duck_type: str,
) -> Optional[Dict[str, Any]]:
    """
    Pop a task from ready_queue[duck_type].
    Returns task payload or None if empty.
    """
    from services.duck_ready_queues import get_ready_queue, fair_select_queue, _ready_queues
    from services.duck_registry import DuckRegistry
    from services.duck_task_scheduler import get_task_scheduler

    # Verify worker is registered and online
    registry = DuckRegistry.get_instance()
    duck = await registry.get(worker_id)
    if not duck or duck.status == DuckStatus.OFFLINE:
        raise ValueError(f"Worker {worker_id} not registered or offline")

    # Check quarantine
    try:
        from services.runtime_metrics import metrics as rm
        if rm.is_quarantined(worker_id):
            return None  # quarantined, no tasks
    except Exception:
        pass

    # Try own type queue first
    q = await get_ready_queue(duck_type)
    item = None
    try:
        item = q.get_nowait()
    except asyncio.QueueEmpty:
        # Try fair select (cross-type assist)
        selected = fair_select_queue()
        if selected and selected != duck_type:
            alt_q = _ready_queues.get(selected)
            if alt_q:
                try:
                    item = alt_q.get_nowait()
                except asyncio.QueueEmpty:
                    pass

    if not item:
        return None  # No tasks available

    # Submit via scheduler (reuse existing logic)
    scheduler = get_task_scheduler()
    task = await scheduler.submit(
        description=item["description"],
        task_type=item["task_type"],
        params=item["params"],
        priority=item["priority"],
        timeout=item["timeout"],
        strategy="direct",
        target_duck_id=worker_id,
        target_duck_type=item.get("duck_type"),
        callback=item.get("callback"),
        source_session_id=item.get("session_id"),
    )

    # Register DAG mapping
    try:
        from services.duck_task_dag import DAGTaskOrchestrator
        orch = DAGTaskOrchestrator.get_instance()
        dag_id = item["dag_id"]
        node_id = item["node_id"]
        execution = orch._executions.get(dag_id)
        if execution:
            node = execution.nodes.get(node_id)
            if node:
                node.task_id = task.task_id
                node.status = TaskStatus.ASSIGNED
            orch._task_to_dag[task.task_id] = (dag_id, node_id)
    except Exception as e:
        logger.warning(f"[remote_pull] DAG mapping error: {e}")

    # Journal
    try:
        from services.runtime_journal import get_journal, TASK_ASSIGNED
        await get_journal().append(
            TASK_ASSIGNED, task_id=task.task_id, duck_id=worker_id
        )
    except Exception:
        pass

    # Metrics
    try:
        from services.runtime_metrics import metrics
        enqueue_time = item.get("enqueue_time", time.time())
        queue_wait = time.time() - enqueue_time
        metrics.record_remote_pull(worker_id, queue_wait)
    except Exception:
        pass

    lease_expiry = time.time() + DEFAULT_LEASE_SECONDS

    logger.info(
        f"[remote_pull] Task {task.task_id} pulled by worker {worker_id} "
        f"(node={item.get('node_id')}, dag={item.get('dag_id')})"
    )

    return {
        "task_id": task.task_id,
        "payload": {
            "description": task.description,
            "task_type": task.task_type,
            "params": task.params,
            "priority": task.priority,
            "timeout": task.timeout,
        },
        "lease_expiry": lease_expiry,
        "dag_id": item.get("dag_id", ""),
        "node_id": item.get("node_id", ""),
    }


# ─── Heartbeat / Lease Renewal ──────────────────────

async def worker_heartbeat(
    worker_id: str,
    running_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Refresh worker heartbeat.
    If running_task_id, extend the task's lease (update last_activity).
    """
    from services.duck_registry import DuckRegistry

    registry = DuckRegistry.get_instance()
    ok = await registry.heartbeat(worker_id)
    if not ok:
        raise ValueError(f"Worker {worker_id} not registered")

    # Extend task lease if provided
    if running_task_id:
        from services.duck_task_scheduler import get_task_scheduler
        scheduler = get_task_scheduler()
        task = scheduler._tasks.get(running_task_id)
        if task and task.assigned_duck_id == worker_id:
            task.last_activity = time.time()

    return {
        "status": "ok",
        "lease_seconds": DEFAULT_LEASE_SECONDS,
    }


# ─── Task Completion ────────────────────────────────

async def complete_task(
    worker_id: str,
    task_id: str,
    result: Any,
    status: str,
) -> Dict[str, Any]:
    """
    Report task completion. Delegates entirely to existing scheduler.handle_result().
    """
    from services.duck_protocol import DuckResultPayload
    from services.duck_task_scheduler import get_task_scheduler

    success = status in ("completed", "success", "ok")

    result_payload = DuckResultPayload(
        task_id=task_id,
        success=success,
        output=result if success else None,
        error=str(result) if not success else None,
    )

    scheduler = get_task_scheduler()
    await scheduler.handle_result(worker_id, result_payload)

    # Metrics
    try:
        from services.runtime_metrics import metrics
        metrics.record_remote_complete(worker_id)
    except Exception:
        pass

    logger.info(
        f"[remote_pull] Task {task_id} completed by worker {worker_id} "
        f"(status={status})"
    )

    return {
        "status": "accepted",
        "task_id": task_id,
    }
