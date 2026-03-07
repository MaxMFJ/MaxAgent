"""
Duck Task Scheduler — 任务调度引擎

功能:
- 任务持久化 (JSON 文件存储)
- 三种调度策略: direct / single-duck / multi-duck
- 结果聚合
- 超时处理
"""
import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from services.duck_protocol import (
    DuckMessage,
    DuckMessageType,
    DuckResultPayload,
    DuckTask,
    DuckTaskPayload,
    DuckType,
    TaskStatus,
)
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)

# 持久化
DATA_DIR = Path(__file__).parent.parent / "data"
TASK_STORE_DIR = DATA_DIR / "duck_tasks"


class ScheduleStrategy:
    """调度策略"""
    DIRECT = "direct"               # 指定 duck
    SINGLE = "single"               # 自动选 1 个空闲 duck
    MULTI = "multi"                 # 拆分子任务给多个 duck


# ─── 结果回调类型 ──────────────────────────────────────
ResultCallback = Callable[[DuckTask], Coroutine[Any, Any, None]]


class DuckTaskScheduler:
    """Duck 任务调度引擎 (单例)"""

    _instance: Optional["DuckTaskScheduler"] = None

    def __init__(self):
        self._tasks: Dict[str, DuckTask] = {}
        self._callbacks: Dict[str, ResultCallback] = {}    # task_id → callback
        self._timeout_handles: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "DuckTaskScheduler":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 初始化 / 持久化 ─────────────────────────────

    async def initialize(self):
        TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self):
        """加载未完成的任务，重启后 ASSIGNED/RUNNING 重置为 PENDING"""
        for fpath in TASK_STORE_DIR.glob("*.json"):
            try:
                raw = json.loads(fpath.read_text(encoding="utf-8"))
                task = DuckTask(**raw)
                if task.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                    # 重启后连接已断开，已分配任务重置为待分配
                    if task.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                        task.status = TaskStatus.PENDING
                        task.assigned_duck_id = None
                        self._persist_task(task)
                    self._tasks[task.task_id] = task
            except Exception as e:
                logger.warning(f"Failed to load task {fpath.name}: {e}")

    def _persist_task(self, task: DuckTask):
        TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
        path = TASK_STORE_DIR / f"{task.task_id}.json"
        path.write_text(
            json.dumps(task.model_dump(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    # ─── 提交任务 ────────────────────────────────────

    async def submit(
        self,
        description: str,
        task_type: str = "general",
        params: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        timeout: int = 600,
        strategy: str = ScheduleStrategy.SINGLE,
        target_duck_id: Optional[str] = None,
        target_duck_type: Optional[DuckType] = None,
        parent_task_id: Optional[str] = None,
        callback: Optional[ResultCallback] = None,
    ) -> DuckTask:
        """提交一个新任务, 返回任务对象"""
        task = DuckTask(
            description=description,
            task_type=task_type,
            params=params or {},
            priority=priority,
            timeout=timeout,
            parent_task_id=parent_task_id,
        )
        async with self._lock:
            self._tasks[task.task_id] = task
            if callback:
                self._callbacks[task.task_id] = callback
            self._persist_task(task)

        logger.info(f"Task submitted: {task.task_id} strategy={strategy}")

        # 调度
        if strategy == ScheduleStrategy.DIRECT:
            await self._schedule_direct(task, target_duck_id)
        elif strategy == ScheduleStrategy.MULTI:
            await self._schedule_multi(task, target_duck_type)
        else:
            await self._schedule_single(task, target_duck_type)

        return task

    # ─── 调度策略 ────────────────────────────────────

    async def _schedule_direct(self, task: DuckTask, duck_id: Optional[str]):
        """直接指定 Duck"""
        if not duck_id:
            await self._fail_task(task, "No duck_id specified for direct strategy")
            return
        await self._assign_to_duck(task, duck_id)

    async def _schedule_single(self, task: DuckTask, duck_type: Optional[DuckType]):
        """从可用池中选一个最合适的 Duck"""
        registry = DuckRegistry.get_instance()
        await registry.initialize()
        candidates = await registry.list_available(duck_type)

        if not candidates:
            logger.warning(f"No available duck for task {task.task_id}, staying PENDING")
            return  # 保持 PENDING, 等 Duck 上线后重新分配

        # 简单选择: 完成任务数最少的 (负载均衡)
        best = min(candidates, key=lambda d: d.completed_tasks + d.failed_tasks)
        await self._assign_to_duck(task, best.duck_id)

    async def _schedule_multi(self, task: DuckTask, duck_type: Optional[DuckType]):
        """拆分任务给多个 Duck (当前为简单 fan-out, 后续可扩展)"""
        registry = DuckRegistry.get_instance()
        await registry.initialize()
        candidates = await registry.list_available(duck_type)

        if not candidates:
            logger.warning(f"No available duck for multi-task {task.task_id}")
            return

        # 当前: 每个 Duck 都执行相同任务, 取最先返回的结果
        # TODO: 支持任务拆分
        for duck in candidates:
            sub_task = DuckTask(
                description=task.description,
                task_type=task.task_type,
                params=task.params,
                priority=task.priority,
                timeout=task.timeout,
                parent_task_id=task.task_id,
            )
            self._tasks[sub_task.task_id] = sub_task
            self._persist_task(sub_task)
            await self._assign_to_duck(sub_task, duck.duck_id)

    # ─── 任务分配 ────────────────────────────────────

    async def _assign_to_duck(self, task: DuckTask, duck_id: str):
        """把任务发送给指定 Duck（自动识别本地/远程）"""
        task.assigned_duck_id = duck_id
        task.assigned_at = time.time()
        task.status = TaskStatus.ASSIGNED
        self._persist_task(task)

        registry = DuckRegistry.get_instance()
        await registry.set_current_task(duck_id, task.task_id, busy_reason="assigned_task")

        payload = DuckTaskPayload(
            task_id=task.task_id,
            description=task.description,
            task_type=task.task_type,
            params=task.params,
            priority=task.priority,
            timeout=task.timeout,
        )

        # 判断是否为本地 Duck
        duck_info = await registry.get(duck_id)
        if duck_info and duck_info.is_local:
            ok = await self._send_to_local_duck(duck_id, payload)
        else:
            ok = await self._send_to_remote_duck(duck_id, payload)

        if not ok:
            logger.warning(f"Failed to send task {task.task_id} to duck {duck_id}")
            task.status = TaskStatus.PENDING
            task.assigned_duck_id = None
            await registry.set_current_task(duck_id, None)
            self._persist_task(task)
            return

        # 启动超时计时
        handle = asyncio.create_task(self._timeout_watcher(task.task_id, task.timeout))
        self._timeout_handles[task.task_id] = handle

        logger.info(f"Task {task.task_id} assigned to duck {duck_id}")

    async def _send_to_local_duck(self, duck_id: str, payload: DuckTaskPayload) -> bool:
        """通过内存队列向本地 Duck 投递任务"""
        try:
            from services.local_duck_worker import get_local_duck_manager
            manager = get_local_duck_manager()
            worker = manager.get_worker(duck_id)
            if not worker:
                return False
            await worker.enqueue_task(payload)
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue task to local duck {duck_id}: {e}")
            return False

    async def _send_to_remote_duck(self, duck_id: str, payload: DuckTaskPayload) -> bool:
        """通过 WebSocket 向远程 Duck 发送任务"""
        from routes.duck_ws import send_to_duck

        msg = DuckMessage(
            type=DuckMessageType.TASK,
            duck_id=duck_id,
            payload=payload.model_dump(),
        )
        return await send_to_duck(duck_id, msg)

    # ─── 结果处理 ────────────────────────────────────

    async def handle_result(self, duck_id: str, result: DuckResultPayload):
        """处理 Duck 返回的任务结果"""
        task = self._tasks.get(result.task_id)
        if not task:
            logger.warning(f"Result for unknown task: {result.task_id}")
            return

        task.output = result.output
        task.error = result.error
        task.completed_at = time.time()
        task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED

        # 取消超时
        handle = self._timeout_handles.pop(result.task_id, None)
        if handle:
            handle.cancel()

        # 更新 registry
        registry = DuckRegistry.get_instance()
        await registry.set_current_task(duck_id, None)
        if result.success:
            await registry.increment_completed(duck_id)
        else:
            await registry.increment_failed(duck_id)

        self._persist_task(task)

        # 聚合子任务结果
        if task.parent_task_id:
            await self._check_parent_completion(task.parent_task_id)

        # 触发回调
        cb = self._callbacks.pop(result.task_id, None)
        if cb:
            try:
                await cb(task)
            except Exception as e:
                logger.error(f"Task callback error: {e}")

        logger.info(f"Task {task.task_id} completed: success={result.success}")

    # ─── 结果聚合 ────────────────────────────────────

    async def _check_parent_completion(self, parent_task_id: str):
        """检查父任务的所有子任务是否完成, 聚合结果"""
        parent = self._tasks.get(parent_task_id)
        if not parent:
            return

        children = [
            t for t in self._tasks.values()
            if t.parent_task_id == parent_task_id
        ]
        if not children:
            return

        all_done = all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            for t in children
        )
        if not all_done:
            return

        # 聚合
        succeeded = [t for t in children if t.status == TaskStatus.COMPLETED]
        failed = [t for t in children if t.status == TaskStatus.FAILED]

        parent.completed_at = time.time()
        if succeeded:
            parent.status = TaskStatus.COMPLETED
            parent.output = {
                "aggregated": True,
                "results": [
                    {"task_id": t.task_id, "duck_id": t.assigned_duck_id, "output": t.output}
                    for t in succeeded
                ],
                "failed_count": len(failed),
            }
        else:
            parent.status = TaskStatus.FAILED
            parent.error = f"All {len(failed)} subtasks failed"
            parent.output = {
                "errors": [
                    {"task_id": t.task_id, "duck_id": t.assigned_duck_id, "error": t.error}
                    for t in failed
                ],
            }

        self._persist_task(parent)

        # 触发父任务回调
        cb = self._callbacks.pop(parent_task_id, None)
        if cb:
            try:
                await cb(parent)
            except Exception as e:
                logger.error(f"Parent task callback error: {e}")

        logger.info(f"Parent task {parent_task_id} aggregated: status={parent.status.value}")

    # ─── 超时处理 ────────────────────────────────────

    async def _timeout_watcher(self, task_id: str, timeout: int):
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        task = self._tasks.get(task_id)
        if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return

        logger.warning(f"Task {task_id} timed out after {timeout}s")
        await self._fail_task(task, f"Task timed out after {timeout}s")

    async def _fail_task(self, task: DuckTask, error: str):
        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = time.time()
        self._persist_task(task)

        if task.assigned_duck_id:
            registry = DuckRegistry.get_instance()
            await registry.set_current_task(task.assigned_duck_id, None)
            await registry.increment_failed(task.assigned_duck_id)

        cb = self._callbacks.pop(task.task_id, None)
        if cb:
            try:
                await cb(task)
            except Exception as e:
                logger.error(f"Task fail callback error: {e}")

    # ─── 取消任务 ────────────────────────────────────

    async def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False

        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()
        self._persist_task(task)

        handle = self._timeout_handles.pop(task_id, None)
        if handle:
            handle.cancel()

        # 通知 Duck 取消
        if task.assigned_duck_id:
            from routes.duck_ws import send_to_duck
            msg = DuckMessage(
                type=DuckMessageType.CANCEL_TASK,
                duck_id=task.assigned_duck_id,
                payload={"task_id": task_id},
            )
            await send_to_duck(task.assigned_duck_id, msg)
            registry = DuckRegistry.get_instance()
            await registry.set_current_task(task.assigned_duck_id, None)

        return True

    # ─── 查询 ────────────────────────────────────────

    async def get_task(self, task_id: str) -> Optional[DuckTask]:
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[DuckTask]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[:limit]

    # ─── 待分配任务重新调度 ──────────────────────────

    async def reschedule_pending(self):
        """重新调度所有 PENDING 任务（Duck 上线时调用）"""
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        for task in pending:
            await self._schedule_single(task, None)


def get_task_scheduler() -> DuckTaskScheduler:
    return DuckTaskScheduler.get_instance()
