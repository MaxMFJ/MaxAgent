"""
Runtime Metrics — In-Memory Metrics Collector for Duck Runtime v2.1

Tracks:
- total_tasks_executed
- avg_queue_wait_time
- avg_exec_time
- retry_rate
- lease_expired_count
- active_workers
- backpressure events
- pull latency

Persistence: 30s JSON snapshot + load on startup.
Expose via get_runtime_metrics() → dict
No external dependencies.
"""

import asyncio
import json
import logging
import time
import threading
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_SNAPSHOT_FILE = _DATA_DIR / "runtime_metrics_snapshot.json"


class RuntimeMetrics:
    """In-memory metrics collector (singleton, thread-safe)"""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()

        # Counters
        self.total_tasks_executed: int = 0
        self.total_tasks_failed: int = 0
        self.total_retries: int = 0
        self.lease_expired_count: int = 0
        self.backpressure_count: int = 0
        self.enqueue_count: int = 0
        self.retry_exhausted_count: int = 0

        # Running averages (exponential moving average)
        self._queue_wait_sum: float = 0.0
        self._queue_wait_count: int = 0
        self._exec_time_sum: float = 0.0
        self._exec_time_count: int = 0
        self._pull_latency_sum: float = 0.0
        self._pull_latency_count: int = 0

        # Active workers
        self._active_workers: Set[str] = set()

        # Per-type counters
        self._type_enqueue: Dict[str, int] = {}
        self._type_backpressure: Dict[str, int] = {}

        # Per-duck health tracking (v2.3)
        self._duck_success: Dict[str, int] = {}
        self._duck_fail: Dict[str, int] = {}
        self._duck_exec_sum: Dict[str, float] = {}
        self._duck_exec_count: Dict[str, int] = {}
        self._duck_lease_expired: Dict[str, int] = {}
        self._quarantined: Dict[str, float] = {}  # duck_id → quarantine_until timestamp
        _QUARANTINE_COOLDOWN = 300  # 5 minutes

        # Slow DAG tracking (v2.3)
        self._dag_exec_times: List[float] = []  # recent DAG execution times
        self.slow_dag_count: int = 0

        # Remote pull tracking (v3.0)
        self.remote_pull_count: int = 0
        self.remote_complete_count: int = 0
        self._remote_workers: Set[str] = set()
        self._remote_exec_sum: float = 0.0
        self._remote_exec_count: int = 0

        # Timestamps
        self._start_time: float = time.time()

    @classmethod
    def get_instance(cls) -> "RuntimeMetrics":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ─── Record Methods ──────────────────────────────

    def record_task_complete(self, exec_time: float, success: bool):
        with self._lock:
            self.total_tasks_executed += 1
            if not success:
                self.total_tasks_failed += 1
            self._exec_time_sum += exec_time
            self._exec_time_count += 1

    def record_pull(self, duck_id: str, queue_wait: float, pull_latency: float):
        with self._lock:
            self._queue_wait_sum += queue_wait
            self._queue_wait_count += 1
            self._pull_latency_sum += pull_latency
            self._pull_latency_count += 1

    def record_enqueue(self, duck_type: str):
        with self._lock:
            self.enqueue_count += 1
            self._type_enqueue[duck_type] = self._type_enqueue.get(duck_type, 0) + 1

    def record_backpressure(self, duck_type: str):
        with self._lock:
            self.backpressure_count += 1
            self._type_backpressure[duck_type] = self._type_backpressure.get(duck_type, 0) + 1

    def record_lease_expired(self):
        with self._lock:
            self.lease_expired_count += 1

    def record_retry(self):
        with self._lock:
            self.total_retries += 1

    def record_dag_exec_time(self, exec_time: float) -> bool:
        """Record DAG execution time. Returns True if slow DAG detected."""
        with self._lock:
            self._dag_exec_times.append(exec_time)
            # Keep last 100 entries for p95 calculation
            if len(self._dag_exec_times) > 100:
                self._dag_exec_times = self._dag_exec_times[-100:]
            # Check if slow (p95 * 3)
            if len(self._dag_exec_times) >= 5:  # need enough samples
                sorted_times = sorted(self._dag_exec_times)
                p95_idx = int(len(sorted_times) * 0.95)
                p95 = sorted_times[min(p95_idx, len(sorted_times) - 1)]
                if exec_time > p95 * 3:
                    self.slow_dag_count += 1
                    return True
            return False

    def record_retry_exhausted(self):
        with self._lock:
            self.retry_exhausted_count += 1

    def worker_start(self, duck_id: str):
        with self._lock:
            self._active_workers.add(duck_id)

    def worker_stop(self, duck_id: str):
        with self._lock:
            self._active_workers.discard(duck_id)

    # ─── Per-Duck Health (v2.3) ──────────────────────

    def record_duck_task_complete(self, duck_id: str, exec_time: float, success: bool):
        with self._lock:
            if success:
                self._duck_success[duck_id] = self._duck_success.get(duck_id, 0) + 1
            else:
                self._duck_fail[duck_id] = self._duck_fail.get(duck_id, 0) + 1
            self._duck_exec_sum[duck_id] = self._duck_exec_sum.get(duck_id, 0.0) + exec_time
            self._duck_exec_count[duck_id] = self._duck_exec_count.get(duck_id, 0) + 1

    def record_duck_lease_expired(self, duck_id: str):
        with self._lock:
            self._duck_lease_expired[duck_id] = self._duck_lease_expired.get(duck_id, 0) + 1

    def get_duck_health_score(self, duck_id: str) -> float:
        """
        Compute health_score ∈ [0, 1] for a duck.
        1.0 = perfect, 0.0 = very unhealthy.
        Factors: success_rate (0.6), avg_exec_time penalty (0.2), lease_expired penalty (0.2)
        """
        with self._lock:
            success = self._duck_success.get(duck_id, 0)
            fail = self._duck_fail.get(duck_id, 0)
            total = success + fail
            if total == 0:
                return 1.0  # no data → assume healthy

            success_rate = success / total

            # Exec time penalty: compare to global average
            duck_exec_count = self._duck_exec_count.get(duck_id, 0)
            duck_avg_exec = (
                self._duck_exec_sum.get(duck_id, 0.0) / duck_exec_count
                if duck_exec_count > 0 else 0.0
            )
            global_avg_exec = (
                self._exec_time_sum / self._exec_time_count
                if self._exec_time_count > 0 else duck_avg_exec or 1.0
            )
            exec_penalty = min(duck_avg_exec / max(global_avg_exec * 3, 1.0), 1.0)

            # Lease expired penalty
            lease_count = self._duck_lease_expired.get(duck_id, 0)
            lease_penalty = min(lease_count / 5.0, 1.0)  # 5+ lease expirations → max penalty

            score = success_rate * 0.6 + (1 - exec_penalty) * 0.2 + (1 - lease_penalty) * 0.2
            return max(0.0, min(1.0, score))

    def quarantine_duck(self, duck_id: str, cooldown: float = 300.0):
        with self._lock:
            self._quarantined[duck_id] = time.time() + cooldown
            logger.warning(f"[worker_health] Duck {duck_id} quarantined for {cooldown}s")

    def is_quarantined(self, duck_id: str) -> bool:
        with self._lock:
            until = self._quarantined.get(duck_id)
            if until is None:
                return False
            if time.time() > until:
                del self._quarantined[duck_id]
                logger.info(f"[worker_health] Duck {duck_id} quarantine lifted")
                return False
            return True

    def get_degraded_workers(self) -> Dict[str, float]:
        """Return all ducks with health_score < 0.5"""
        degraded = {}
        for duck_id in set(list(self._duck_success.keys()) + list(self._duck_fail.keys())):
            score = self.get_duck_health_score(duck_id)
            if score < 0.5:
                degraded[duck_id] = score
        return degraded

    # ─── Remote Pull Metrics (v3.0) ─────────────────

    def record_remote_worker_register(self, worker_id: str):
        with self._lock:
            self._remote_workers.add(worker_id)

    def record_remote_pull(self, worker_id: str, queue_wait: float):
        with self._lock:
            self.remote_pull_count += 1
            self._remote_exec_sum += queue_wait
            self._remote_exec_count += 1

    def record_remote_complete(self, worker_id: str):
        with self._lock:
            self.remote_complete_count += 1

    # ─── Query ───────────────────────────────────────

    def get_metrics(self) -> Dict:
        with self._lock:
            uptime = time.time() - self._start_time
            avg_queue_wait = (
                self._queue_wait_sum / self._queue_wait_count
                if self._queue_wait_count > 0 else 0.0
            )
            avg_exec_time = (
                self._exec_time_sum / self._exec_time_count
                if self._exec_time_count > 0 else 0.0
            )
            avg_pull_latency = (
                self._pull_latency_sum / self._pull_latency_count
                if self._pull_latency_count > 0 else 0.0
            )
            retry_rate = (
                self.total_retries / self.total_tasks_executed
                if self.total_tasks_executed > 0 else 0.0
            )

            return {
                "uptime_seconds": round(uptime, 1),
                "total_tasks_executed": self.total_tasks_executed,
                "total_tasks_failed": self.total_tasks_failed,
                "total_retries": self.total_retries,
                "retry_rate": round(retry_rate, 4),
                "lease_expired_count": self.lease_expired_count,
                "backpressure_count": self.backpressure_count,
                "enqueue_count": self.enqueue_count,
                "retry_exhausted_count": self.retry_exhausted_count,
                "active_workers": len(self._active_workers),
                "active_worker_ids": sorted(self._active_workers),
                "avg_queue_wait_time": round(avg_queue_wait, 3),
                "avg_exec_time": round(avg_exec_time, 3),
                "avg_pull_latency": round(avg_pull_latency, 3),
                "per_type_enqueue": dict(self._type_enqueue),
                "per_type_backpressure": dict(self._type_backpressure),
                # v3.0 remote metrics
                "remote_pull_count": self.remote_pull_count,
                "remote_worker_count": len(self._remote_workers),
                "remote_exec_latency": round(
                    self._remote_exec_sum / self._remote_exec_count
                    if self._remote_exec_count > 0 else 0.0, 3
                ),
            }

    def reset(self):
        """Reset all metrics (for testing)"""
        with self._lock:
            self.__init__()

    # ─── Persistence ─────────────────────────────────

    def persist_snapshot(self):
        """Save metrics snapshot to JSON file (sync, call from executor)"""
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = self.get_metrics()
            data["snapshot_time"] = time.time()
            with open(_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[metrics] Snapshot persist failed: {e}")

    def load_snapshot(self):
        """Load counters from previous snapshot (call on startup)"""
        if not _SNAPSHOT_FILE.exists():
            return
        try:
            with open(_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self.total_tasks_executed = data.get("total_tasks_executed", 0)
                self.total_tasks_failed = data.get("total_tasks_failed", 0)
                self.total_retries = data.get("total_retries", 0)
                self.lease_expired_count = data.get("lease_expired_count", 0)
                self.backpressure_count = data.get("backpressure_count", 0)
                self.enqueue_count = data.get("enqueue_count", 0)
                self._type_enqueue = data.get("per_type_enqueue", {})
                self._type_backpressure = data.get("per_type_backpressure", {})
            logger.info(f"[metrics] Loaded snapshot: executed={self.total_tasks_executed}")
        except Exception as e:
            logger.warning(f"[metrics] Snapshot load failed: {e}")


# ─── Module-level singleton ──────────────────────────
metrics = RuntimeMetrics.get_instance()


def get_runtime_metrics() -> Dict:
    """获取运行时指标快照"""
    return metrics.get_metrics()


# ─── Periodic Snapshot Coroutine ─────────────────────
_snapshot_task = None


async def _snapshot_loop(interval: float = 30.0):
    """每 interval 秒持久化一次 metrics 快照"""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(interval)
        try:
            await loop.run_in_executor(None, metrics.persist_snapshot)
        except Exception as e:
            logger.warning(f"[metrics] Snapshot loop error: {e}")


def start_metrics_snapshot_loop(interval: float = 30.0):
    """启动 30s 指标快照循环"""
    global _snapshot_task
    if _snapshot_task is not None:
        return
    # Load previous snapshot on startup
    metrics.load_snapshot()
    _snapshot_task = asyncio.create_task(_snapshot_loop(interval))
    logger.info(f"[metrics] Snapshot loop started (interval={interval}s)")
