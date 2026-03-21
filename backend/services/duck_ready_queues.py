"""
Duck Ready Queues — Pull-Based Runtime v2.1

Typed async queues for each duck type with production guarantees:
- Backpressure: bounded queues with overflow → pending retry
- Fair scheduling: weighted round-robin across duck types
- Graceful shutdown: queue snapshot persistence + drain
- Metrics integration via runtime_metrics

Flow:
  DAG node deps satisfied → enqueue_ready_node() → ready_queues[type].put()
  Duck ONLINE → worker_pull_loop() → ready_queues[type].get() → assign
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.duck_protocol import DuckStatus, DuckType, TaskStatus

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────
DEFAULT_QUEUE_MAXSIZE = 100

# 每个 duck_type 的 maxsize（可覆盖）
ready_queue_config: Dict[str, int] = {}

# 公平调度权重（值越大在轮转中出现次数越多）
fair_weights: Dict[str, int] = {
    "coder": 2,
    "designer": 1,
    "crawler": 1,
    "tester": 1,
    "general": 1,
}

# Shutdown 控制
_shutdown_event = asyncio.Event()
_accepting_new = True

# Queue snapshot 持久化路径
_SNAPSHOT_DIR = Path(__file__).parent.parent / "data"
_SNAPSHOT_FILE = _SNAPSHOT_DIR / "ready_queue_snapshot.json"


# ─── Typed Ready Queues ──────────────────────────────
_ready_queues: Dict[str, asyncio.Queue] = {}
_overflow_pending: Dict[str, List[dict]] = {}  # backpressure: 溢出暂存
_queue_lock = asyncio.Lock()

# ─── Adaptive Backpressure (v2.3) ────────────────────
PRESSURE_THRESHOLD = 0.8


def compute_pressure_score() -> float:
    """
    Global system pressure: 0.0 (idle) → 1.0 (overloaded)
    pressure = queue_fill_ratio * 0.5 + active_workers_ratio * 0.3 + retry_rate * 0.2
    """
    # Queue fill ratio
    total_capacity = 0
    total_used = 0
    for dtype, q in _ready_queues.items():
        maxsize = q.maxsize if q.maxsize > 0 else DEFAULT_QUEUE_MAXSIZE
        total_capacity += maxsize
        total_used += q.qsize()
    for pending_list in _overflow_pending.values():
        total_used += len(pending_list)
    queue_fill = total_used / max(total_capacity, 1)

    # Active workers ratio
    active_workers = len(_pull_tasks)
    total_workers = max(active_workers, 1)
    # Count busy workers (those that are in _pull_tasks and currently assigned)
    workers_ratio = min(active_workers / max(total_workers, 1), 1.0)

    # Retry rate from metrics
    retry_rate = 0.0
    try:
        from services.runtime_metrics import metrics
        m = metrics.get_metrics()
        retry_rate = m.get("retry_rate", 0.0)
    except Exception:
        pass

    pressure = queue_fill * 0.5 + workers_ratio * 0.3 + retry_rate * 0.2
    return min(pressure, 1.0)


def is_system_overloaded() -> bool:
    """Check if system is under high pressure"""
    return compute_pressure_score() > PRESSURE_THRESHOLD


async def get_ready_queue(duck_type_value: str) -> asyncio.Queue:
    """获取或懒创建某类型的 bounded ready queue"""
    if duck_type_value not in _ready_queues:
        async with _queue_lock:
            if duck_type_value not in _ready_queues:
                maxsize = ready_queue_config.get(duck_type_value, DEFAULT_QUEUE_MAXSIZE)
                _ready_queues[duck_type_value] = asyncio.Queue(maxsize=maxsize)
                _overflow_pending[duck_type_value] = []
                logger.info(
                    f"[ready_queue] Created bounded queue for '{duck_type_value}' "
                    f"(maxsize={maxsize})"
                )
    return _ready_queues[duck_type_value]


async def enqueue_ready_node(
    dag_id: str,
    node_id: str,
    description: str,
    task_type: str,
    params: Dict[str, Any],
    priority: int,
    timeout: int,
    duck_type: Optional[DuckType],
    duck_id: Optional[str],
    callback: Optional[Callable],
    session_id: str = "",
) -> bool:
    """将已就绪的 DAG 节点放入 ready queue，满时溢出到 pending list"""
    global _accepting_new
    if not _accepting_new:
        logger.warning(f"[ready_queue] Rejecting enqueue (shutdown in progress): node={node_id}")
        return False

    type_key = duck_type.value if duck_type else "general"
    q = await get_ready_queue(type_key)

    item = {
        "dag_id": dag_id,
        "node_id": node_id,
        "description": description,
        "task_type": task_type,
        "params": params,
        "priority": priority,
        "timeout": timeout,
        "duck_type": duck_type,
        "duck_id": duck_id,
        "callback": callback,
        "session_id": session_id,
        "enqueue_time": time.time(),
    }

    try:
        q.put_nowait(item)
        # Metrics
        try:
            from services.runtime_metrics import metrics
            metrics.record_enqueue(type_key)
        except Exception:
            pass
    except asyncio.QueueFull:
        # Backpressure: 溢出到 pending list
        logger.warning(
            f"[backpressure] Queue '{type_key}' full (size={q.qsize()}), "
            f"node {node_id} moved to overflow pending"
        )
        _overflow_pending.setdefault(type_key, []).append(item)
        try:
            from services.runtime_metrics import metrics
            metrics.record_backpressure(type_key)
        except Exception:
            pass
        return True

    logger.info(
        f"[ready_queue] Enqueued node {node_id} (dag={dag_id}) → queue '{type_key}' "
        f"(queue_size={q.qsize()})"
    )

    # Journal: TASK_ENQUEUED
    try:
        from services.runtime_journal import get_journal, TASK_ENQUEUED
        await get_journal().append(TASK_ENQUEUED, node_id=node_id, dag_id=dag_id,
                                   extra={"duck_type": type_key})
    except Exception:
        pass
    return True


def _rebuild_dag_callback(dag_id: str, node_id: str) -> Optional[Callable]:
    """Rebuild DAG completion callback for queue items restored after restart."""
    if not dag_id or not node_id:
        return None

    from services.duck_task_dag import DAGTaskOrchestrator
    from services.duck_protocol import DuckTask

    orchestrator = DAGTaskOrchestrator.get_instance()
    execution = orchestrator.get_execution(dag_id)
    if not execution or node_id not in execution.nodes:
        return None

    async def on_complete(task: DuckTask, _dag_id=dag_id, _node_id=node_id):
        await orchestrator._on_node_complete(_dag_id, _node_id, task)

    return on_complete


async def load_queue_snapshot() -> Dict[str, int]:
    """Restore queue items persisted during the previous shutdown."""
    if not _SNAPSHOT_FILE.exists():
        return {"restored": 0, "skipped": 0}

    restored = 0
    skipped = 0

    try:
        snapshot = json.loads(_SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[recovery] Failed to load ready queue snapshot: {e}")
        return {"restored": 0, "skipped": 0}

    for type_key, items in snapshot.items():
        q = await get_ready_queue(type_key)
        for raw in items or []:
            item = dict(raw)
            duck_type_value = item.get("duck_type")
            if duck_type_value:
                try:
                    item["duck_type"] = DuckType(duck_type_value)
                except ValueError:
                    item["duck_type"] = None

            dag_id = item.get("dag_id", "")
            node_id = item.get("node_id", "")
            item["callback"] = _rebuild_dag_callback(dag_id, node_id)

            if dag_id and node_id:
                from services.duck_task_dag import DAGTaskOrchestrator

                execution = DAGTaskOrchestrator.get_instance().get_execution(dag_id)
                node = execution.nodes.get(node_id) if execution else None
                if not node:
                    skipped += 1
                    logger.warning(
                        f"[recovery] Skipping stale ready queue item dag={dag_id} node={node_id}"
                    )
                    continue
                node.execution_emitted = True
                node.task_id = None
                node.status = TaskStatus.ENQUEUED

            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                _overflow_pending.setdefault(type_key, []).append(item)
            restored += 1

    try:
        _SNAPSHOT_FILE.unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[recovery] Failed to remove ready queue snapshot: {e}")

    if restored or skipped:
        logger.info(
            f"[recovery] Ready queue snapshot restored: restored={restored} skipped={skipped}"
        )
    return {"restored": restored, "skipped": skipped}


async def _drain_overflow():
    """尝试将溢出 pending list 中的任务放回 queue（由 watchdog 调用）"""
    for type_key, pending_list in _overflow_pending.items():
        if not pending_list:
            continue
        q = _ready_queues.get(type_key)
        if not q:
            continue
        drained = 0
        while pending_list and not q.full():
            item = pending_list.pop(0)
            try:
                q.put_nowait(item)
                drained += 1
            except asyncio.QueueFull:
                pending_list.insert(0, item)
                break
        if drained:
            logger.info(f"[backpressure] Drained {drained} overflow items → queue '{type_key}'")


# ─── Fair Round-Robin Coordinator ────────────────────
_round_robin_order: List[str] = []
_rr_index: int = 0


def _build_round_robin():
    """根据 fair_weights 构建轮转序列"""
    global _round_robin_order
    order = []
    for dtype, weight in fair_weights.items():
        order.extend([dtype] * weight)
    _round_robin_order = order


def fair_select_queue() -> Optional[str]:
    """公平选择下一个有任务的 queue type（加权轮转）"""
    global _rr_index
    if not _round_robin_order:
        _build_round_robin()

    n = len(_round_robin_order)
    for _ in range(n):
        idx = _rr_index % n
        _rr_index += 1
        dtype = _round_robin_order[idx]
        q = _ready_queues.get(dtype)
        if q and not q.empty():
            return dtype

    # Fallback: 检查不在 weights 中但有任务的队列
    for dtype, q in _ready_queues.items():
        if not q.empty():
            return dtype
    return None


# ─── Worker Pull Loops ──────────────────────────────
# duck_id → (asyncio.Task, asyncio.Event)
_pull_tasks: Dict[str, Tuple[asyncio.Task, asyncio.Event]] = {}


async def worker_pull_loop(duck_id: str, duck_type_value: str, stop_event: asyncio.Event):
    """
    单个 Duck 的 pull 循环。优先从自己类型的 queue pull，
    空闲时也可从 fair_select 抢其他类型任务。
    """
    from services.duck_task_scheduler import get_task_scheduler
    from services.duck_registry import DuckRegistry

    logger.info(f"[pull_loop] Duck {duck_id} started pull loop on queue '{duck_type_value}'")

    # Metrics: 记录 worker 活跃
    try:
        from services.runtime_metrics import metrics
        metrics.worker_start(duck_id)
    except Exception:
        pass

    while not stop_event.is_set() and not _shutdown_event.is_set():
        try:
            # v2.3: Check quarantine
            try:
                from services.runtime_metrics import metrics as _rm
                if _rm.is_quarantined(duck_id):
                    await asyncio.sleep(10)
                    continue
            except Exception:
                pass

            # 优先从自身类型 queue pull
            q = await get_ready_queue(duck_type_value)
            item = None

            try:
                item = await asyncio.wait_for(q.get(), timeout=2.0)
            except asyncio.TimeoutError:
                # 也尝试从公平轮转中获取（跨类型协助）
                selected = fair_select_queue()
                if selected and selected != duck_type_value:
                    alt_q = _ready_queues.get(selected)
                    if alt_q:
                        try:
                            item = alt_q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                if not item:
                    continue

            if stop_event.is_set() or _shutdown_event.is_set():
                if item:
                    await q.put(item)
                break

            enqueue_time = item.get("enqueue_time", time.time())
            queue_wait = time.time() - enqueue_time

            # 检查 duck 仍然在线且空闲
            registry = DuckRegistry.get_instance()
            duck = await registry.get(duck_id)
            if not duck or duck.status != DuckStatus.ONLINE:
                # 放回队列
                type_key = item.get("duck_type")
                requeue_key = type_key.value if type_key else duck_type_value
                rq = await get_ready_queue(requeue_key)
                try:
                    rq.put_nowait(item)
                except asyncio.QueueFull:
                    _overflow_pending.setdefault(requeue_key, []).append(item)
                logger.info(f"[pull_loop] Duck {duck_id} unavailable, item re-queued")
                await asyncio.sleep(1)
                continue

            # Submit via scheduler (保留持久化 + 回调 + 超时)
            scheduler = get_task_scheduler()
            pull_start = time.time()

            task = await scheduler.submit(
                description=item["description"],
                task_type=item["task_type"],
                params=item["params"],
                priority=item["priority"],
                timeout=item["timeout"],
                strategy="direct",
                target_duck_id=duck_id,
                target_duck_type=item["duck_type"],
                callback=item.get("callback"),
                source_session_id=item.get("session_id"),
            )

            pull_latency = time.time() - pull_start

            # Metrics
            try:
                from services.runtime_metrics import metrics
                metrics.record_pull(duck_id, queue_wait, pull_latency)
            except Exception:
                pass

            logger.info(
                f"[metrics] Pull assigned: duck={duck_id} task={task.task_id} "
                f"node={item['node_id']} queue_wait={queue_wait:.1f}s "
                f"pull_latency={pull_latency:.3f}s"
            )

            # 注册 DAG 映射
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
                        node.duck_id = duck_id
                    orch._task_to_dag[task.task_id] = (dag_id, node_id)

                    # 群聊: 通知任务分配（pull 路径根节点不经过 _schedule_ready_nodes）
                    if node:
                        try:
                            await orch._group_post_task_assign(execution, node)
                        except Exception as ge:
                            logger.debug(f"[pull_loop] group assign msg failed: {ge}")
            except Exception as e:
                logger.warning(f"[pull_loop] DAG mapping error: {e}")

            # 等待 duck 完成当前任务后再 pull 下一个
            await _wait_duck_free(duck_id, stop_event)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[pull_loop] Duck {duck_id} error: {e}", exc_info=True)
            await asyncio.sleep(2)

    # Metrics: worker 停止
    try:
        from services.runtime_metrics import metrics
        metrics.worker_stop(duck_id)
    except Exception:
        pass

    logger.info(f"[pull_loop] Duck {duck_id} pull loop stopped")


async def _wait_duck_free(duck_id: str, stop_event: asyncio.Event, max_wait: int = 900):
    """等待 duck 变为空闲"""
    from services.duck_registry import DuckRegistry

    start = time.time()
    while not stop_event.is_set() and not _shutdown_event.is_set():
        duck = await DuckRegistry.get_instance().get(duck_id)
        if not duck or duck.status != DuckStatus.BUSY:
            idle_time = time.time() - start
            if idle_time > 0.5:
                logger.info(f"[metrics] Duck {duck_id} worker_idle_time={idle_time:.1f}s")
            return
        if time.time() - start > max_wait:
            logger.warning(f"[pull_loop] Duck {duck_id} busy >{max_wait}s, breaking wait")
            return
        await asyncio.sleep(1)


def start_pull_loop(duck_id: str, duck_type_value: str) -> asyncio.Event:
    """启动 duck 的 pull loop，返回 stop_event"""
    stop_event = asyncio.Event()
    stop_pull_loop(duck_id)
    task = asyncio.create_task(worker_pull_loop(duck_id, duck_type_value, stop_event))
    _pull_tasks[duck_id] = (task, stop_event)
    return stop_event


def stop_pull_loop(duck_id: str):
    """停止 duck 的 pull loop"""
    entry = _pull_tasks.pop(duck_id, None)
    if entry:
        task, stop_event = entry
        stop_event.set()
        task.cancel()
        logger.info(f"[pull_loop] Duck {duck_id} pull loop cancelled")


# ─── Overflow Drain Loop ────────────────────────────
_overflow_drain_task: Optional[asyncio.Task] = None


def start_overflow_drain_loop():
    """后台定期将溢出 pending 放回队列"""
    global _overflow_drain_task
    if _overflow_drain_task and not _overflow_drain_task.done():
        return

    async def _loop():
        while not _shutdown_event.is_set():
            await asyncio.sleep(5)
            try:
                await _drain_overflow()
            except Exception as e:
                logger.warning(f"[overflow_drain] error: {e}")

    _overflow_drain_task = asyncio.create_task(_loop())


# ─── Graceful Shutdown ──────────────────────────────

async def graceful_shutdown(timeout: float = 30.0):
    """
    优雅关停：
    1. 停止接受新任务
    2. 等待活跃 worker 完成（最长 timeout 秒）
    3. 取消剩余 pull loops
    4. 持久化队列快照
    """
    global _accepting_new
    _accepting_new = False
    _shutdown_event.set()
    logger.info("[shutdown] Ready queues: stopping new enqueues, draining workers...")

    # 等待所有 pull loop 停止
    tasks = []
    for duck_id, (task, stop_event) in list(_pull_tasks.items()):
        stop_event.set()
        tasks.append(task)

    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=timeout)
        for t in pending:
            t.cancel()
        logger.info(f"[shutdown] {len(done)} workers drained, {len(pending)} cancelled")

    _pull_tasks.clear()

    # 持久化队列快照
    await _persist_queue_snapshot()

    # 停止 overflow drain
    if _overflow_drain_task and not _overflow_drain_task.done():
        _overflow_drain_task.cancel()

    logger.info("[shutdown] Ready queues shutdown complete")


async def _persist_queue_snapshot():
    """将所有 queue 中未处理的 item 持久化到 JSON"""
    snapshot: Dict[str, list] = {}

    for type_key, q in _ready_queues.items():
        items = []
        while not q.empty():
            try:
                item = q.get_nowait()
                # callback 不可序列化，记录 dag_id + node_id 用于恢复
                serializable = {
                    k: (v.value if isinstance(v, DuckType) else v)
                    for k, v in item.items()
                    if k != "callback"
                }
                items.append(serializable)
            except asyncio.QueueEmpty:
                break
        # 加上 overflow pending
        for ovf in _overflow_pending.get(type_key, []):
            serializable = {
                k: (v.value if isinstance(v, DuckType) else v)
                for k, v in ovf.items()
                if k != "callback"
            }
            items.append(serializable)
        if items:
            snapshot[type_key] = items

    if snapshot:
        try:
            _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            _SNAPSHOT_FILE.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            total = sum(len(v) for v in snapshot.values())
            logger.info(f"[shutdown] Persisted {total} queue items to {_SNAPSHOT_FILE}")
        except Exception as e:
            logger.error(f"[shutdown] Failed to persist queue snapshot: {e}")


# ─── Query / Monitoring ─────────────────────────────

def get_all_queue_sizes() -> Dict[str, int]:
    """获取所有 ready queue 的当前长度"""
    return {k: q.qsize() for k, q in _ready_queues.items()}


def get_overflow_sizes() -> Dict[str, int]:
    """获取所有 overflow pending 的长度"""
    return {k: len(v) for k, v in _overflow_pending.items() if v}


def get_active_pull_loops() -> List[str]:
    """获取活跃的 pull loop duck_id 列表"""
    return [did for did, (t, _) in _pull_tasks.items() if not t.done()]
