"""
Runtime Health — Fast health snapshot & diagnostics for /runtime/* endpoints (v3.0 Final)

All data from in-memory sources. No blocking IO.
Includes: health snapshot, task explain, queue state, worker diagnostics,
          stuck task detection, readiness levels.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Stuck Task Detector State ───────────────────────
_stuck_detector_task: Optional[asyncio.Task] = None
_suspected_stuck: Dict[str, float] = {}  # task_id → detected_at timestamp


def get_runtime_health() -> Dict[str, Any]:
    """
    Compute fast runtime health snapshot with readiness levels.
    Returns:
      status (OK/DEGRADED/CRITICAL), reasons, pressure, active_workers,
      queue_sizes, avg_latency, degraded_workers, journal_size_mb,
      suspected_stuck_tasks
    """
    result: Dict[str, Any] = {}
    reasons: List[str] = []

    # 1. Pressure score
    try:
        from services.duck_ready_queues import compute_pressure_score, _ready_queues
        result["pressure"] = round(compute_pressure_score(), 3)
        result["queue_sizes"] = {k: q.qsize() for k, q in _ready_queues.items()}
    except Exception:
        result["pressure"] = -1
        result["queue_sizes"] = {}

    # 2. Runtime metrics
    active_workers = 0
    try:
        from services.runtime_metrics import metrics
        m = metrics.get_metrics()
        active_workers = m.get("active_workers", 0)
        result["active_workers"] = active_workers
        result["active_worker_ids"] = m.get("active_worker_ids", [])
        result["avg_latency"] = m.get("avg_exec_time", 0)
        result["avg_queue_wait"] = m.get("avg_queue_wait_time", 0)
        result["total_tasks_executed"] = m.get("total_tasks_executed", 0)
        result["total_tasks_failed"] = m.get("total_tasks_failed", 0)
        result["retry_exhausted_count"] = m.get("retry_exhausted_count", 0)
        result["lease_expired_count"] = m.get("lease_expired_count", 0)
        result["backpressure_count"] = m.get("backpressure_count", 0)
    except Exception:
        result["active_workers"] = 0
        result["avg_latency"] = 0

    # 3. Degraded workers
    degraded = {}
    try:
        from services.runtime_metrics import metrics as rt_m
        degraded = rt_m.get_degraded_workers()
        result["degraded_workers"] = degraded
    except Exception:
        result["degraded_workers"] = {}

    # 4. Journal size (lightweight stat, no read)
    try:
        from pathlib import Path
        journal_path = Path(__file__).parent.parent / "data" / "runtime_journal.log"
        if journal_path.exists():
            result["journal_size_mb"] = round(journal_path.stat().st_size / (1024 * 1024), 2)
        else:
            result["journal_size_mb"] = 0
    except Exception:
        result["journal_size_mb"] = -1

    # 5. Slow DAG count
    try:
        from services.runtime_metrics import metrics as rt_m2
        result["slow_dag_count"] = rt_m2.slow_dag_count
    except Exception:
        result["slow_dag_count"] = 0

    # 6. Suspected stuck tasks
    result["suspected_stuck_tasks"] = len(_suspected_stuck)

    # 7. Overflow growing check
    overflow_total = 0
    try:
        from services.duck_ready_queues import get_overflow_sizes
        overflow = get_overflow_sizes()
        overflow_total = sum(overflow.values())
        result["overflow_total"] = overflow_total
    except Exception:
        result["overflow_total"] = 0

    # ─── Readiness Levels ────────────────────────────
    pressure = result.get("pressure", 0)

    # CRITICAL conditions
    if active_workers == 0:
        reasons.append("no_active_workers")
    if overflow_total > 50:
        reasons.append("overflow_growing")
    if result.get("lease_expired_count", 0) > 10:
        reasons.append("lease_expired_spike")
    if pressure > 0.95:
        reasons.append("extreme_pressure")

    # DEGRADED conditions
    if result.get("retry_exhausted_count", 0) > 3:
        reasons.append("retries_exhausted")
    if len(_suspected_stuck) > 0:
        reasons.append("stuck_tasks_detected")
    if len(degraded) > 0:
        reasons.append("degraded_workers_present")
    if 0.8 < pressure <= 0.95:
        reasons.append("high_pressure")

    # Determine status
    critical_reasons = {"no_active_workers", "overflow_growing", "lease_expired_spike", "extreme_pressure"}
    if reasons and critical_reasons & set(reasons):
        status = "CRITICAL"
    elif reasons:
        status = "DEGRADED"
    else:
        status = "OK"

    result["status"] = status
    result["reasons"] = reasons

    return result


def get_task_explain(task_id: str) -> Optional[Dict[str, Any]]:
    """
    Explain a single task: status, owner, retries, timings, journal events.
    Returns None if task not found.
    """
    try:
        from services.duck_task_scheduler import DuckTaskScheduler
        scheduler = DuckTaskScheduler.get_instance()
        task = scheduler._tasks.get(task_id)
    except Exception:
        return None

    if not task:
        return None

    now = time.time()
    info: Dict[str, Any] = {
        "task_id": task.task_id,
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "task_type": task.task_type,
        "description": (task.description or "")[:200],
        "assigned_duck_id": task.assigned_duck_id,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "priority": task.priority,
        "created_at": task.created_at,
        "assigned_at": task.assigned_at,
        "completed_at": task.completed_at,
        "last_activity": task.last_activity,
    }

    # Timing calculations
    if task.assigned_at and task.created_at:
        info["queue_wait_s"] = round(task.assigned_at - task.created_at, 2)
    if task.completed_at and task.assigned_at:
        info["execution_s"] = round(task.completed_at - task.assigned_at, 2)
    if not task.completed_at and task.created_at:
        info["age_s"] = round(now - task.created_at, 2)

    # Stuck?
    info["suspected_stuck"] = task_id in _suspected_stuck

    # Last 10 journal events for this task
    try:
        from services.runtime_journal import RuntimeJournal
        journal = RuntimeJournal.get_instance()
        all_entries = journal.read_all()
        task_entries = [e for e in all_entries if e.get("task_id") == task_id]
        info["journal_events"] = task_entries[-10:]
    except Exception:
        info["journal_events"] = []

    return info


def get_queue_state() -> Dict[str, Any]:
    """
    Full queue state: per-type sizes, overflow, active workers, backpressure.
    """
    result: Dict[str, Any] = {}

    try:
        from services.duck_ready_queues import (
            _ready_queues, _overflow_pending, _pull_tasks,
            compute_pressure_score, is_system_overloaded,
            DEFAULT_QUEUE_MAXSIZE, ready_queue_config,
        )
        queues = {}
        for dtype, q in _ready_queues.items():
            maxsize = ready_queue_config.get(dtype, DEFAULT_QUEUE_MAXSIZE)
            queues[dtype] = {
                "size": q.qsize(),
                "maxsize": maxsize,
                "fill_ratio": round(q.qsize() / max(maxsize, 1), 3),
                "overflow": len(_overflow_pending.get(dtype, [])),
            }
        result["queues"] = queues
        result["pressure"] = round(compute_pressure_score(), 3)
        result["overloaded"] = is_system_overloaded()
        result["active_pull_loops"] = [
            did for did, (t, _) in _pull_tasks.items() if not t.done()
        ]
    except Exception as e:
        result["error"] = str(e)

    return result


def get_worker_diagnostics() -> List[Dict[str, Any]]:
    """
    Per-worker diagnostics: duck_type, is_local, assigned_task, health, lease info.
    """
    workers: List[Dict[str, Any]] = []
    now = time.time()

    try:
        from services.duck_registry import DuckRegistry
        from services.duck_protocol import DuckStatus
        registry = DuckRegistry.get_instance()

        for duck_id, duck in registry._ducks.items():
            w: Dict[str, Any] = {
                "duck_id": duck_id,
                "duck_type": duck.duck_type.value if hasattr(duck.duck_type, "value") else str(duck.duck_type),
                "is_local": getattr(duck, "is_local", True),
                "status": duck.status.value if hasattr(duck.status, "value") else str(duck.status),
                "current_task_id": duck.current_task_id,
                "completed_tasks": duck.completed_tasks,
                "failed_tasks": duck.failed_tasks,
            }

            # Last heartbeat / lease
            last_hb = getattr(duck, "last_heartbeat", None) or getattr(duck, "registered_at", None)
            if last_hb:
                w["last_heartbeat_age_s"] = round(now - last_hb, 1)

            # Lease remaining if assigned
            if duck.current_task_id:
                try:
                    from services.duck_task_scheduler import DuckTaskScheduler
                    scheduler = DuckTaskScheduler.get_instance()
                    task = scheduler._tasks.get(duck.current_task_id)
                    if task and task.last_activity:
                        remaining = scheduler._lease_timeout - (now - task.last_activity)
                        w["lease_remaining_s"] = round(max(remaining, 0), 1)
                except Exception:
                    pass

            # Health score
            try:
                from services.runtime_metrics import metrics
                w["health_score"] = round(metrics.get_duck_health_score(duck_id), 3)
                w["quarantined"] = metrics.is_quarantined(duck_id)
            except Exception:
                w["health_score"] = 1.0
                w["quarantined"] = False

            # Worker status classification
            if w.get("quarantined"):
                w["worker_status"] = "QUARANTINED"
            elif w.get("last_heartbeat_age_s", 0) > 120:
                w["worker_status"] = "LOST"
            elif w.get("last_heartbeat_age_s", 0) > 60:
                w["worker_status"] = "STALE"
            elif w.get("health_score", 1.0) < 0.3:
                w["worker_status"] = "DEGRADED"
            else:
                w["worker_status"] = "HEALTHY"

            workers.append(w)

    except Exception as e:
        logger.warning(f"[worker_diagnostics] error: {e}")

    return workers


# ─── Stuck Task Detector ─────────────────────────────

def start_stuck_task_detector(interval: float = 30.0):
    """Start background coroutine that detects stuck tasks every N seconds."""
    global _stuck_detector_task
    if _stuck_detector_task and not _stuck_detector_task.done():
        return

    async def _detector_loop():
        while True:
            await asyncio.sleep(interval)
            try:
                _detect_stuck_tasks()
            except Exception as e:
                logger.warning(f"[stuck_detector] error: {e}")

    _stuck_detector_task = asyncio.create_task(_detector_loop())
    logger.info(f"[stuck_detector] Started (interval={interval}s)")


def _detect_stuck_tasks():
    """
    Scan ASSIGNED/RUNNING tasks. If no activity for > lease_timeout * 0.8,
    mark as suspected stuck.
    """
    global _suspected_stuck
    now = time.time()
    new_stuck: Dict[str, float] = {}

    try:
        from services.duck_task_scheduler import DuckTaskScheduler
        from services.duck_protocol import TaskStatus
        scheduler = DuckTaskScheduler.get_instance()
        threshold = scheduler._lease_timeout * 0.8

        for task_id, task in scheduler._tasks.items():
            if task.status not in (TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                continue
            base = task.last_activity or task.assigned_at or task.created_at
            if now - base > threshold:
                new_stuck[task_id] = _suspected_stuck.get(task_id, now)

    except Exception as e:
        logger.warning(f"[stuck_detector] scan error: {e}")
        return

    if new_stuck != _suspected_stuck:
        added = set(new_stuck) - set(_suspected_stuck)
        cleared = set(_suspected_stuck) - set(new_stuck)
        if added:
            logger.warning(f"[stuck_detector] New stuck tasks: {added}")
        if cleared:
            logger.info(f"[stuck_detector] Cleared stuck tasks: {cleared}")

    _suspected_stuck = new_stuck
