"""
Local Duck Worker — 本地 Duck 运行时

在同一进程中以 asyncio 任务运行的 Duck Agent。
每个 Local Duck 有独立的任务队列，通过内存直接与调度器通信，
无需 WebSocket。
"""
import asyncio
import logging
import platform
import socket
import time
import uuid
from typing import Any, Dict, Optional

from services.duck_protocol import (
    DuckInfo,
    DuckResultPayload,
    DuckStatus,
    DuckTask,
    DuckTaskPayload,
    DuckType,
    TaskStatus,
)
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)


class LocalDuckWorker:
    """单个本地 Duck 工作线程（asyncio 协程）"""

    def __init__(
        self,
        duck_id: str,
        name: str,
        duck_type: DuckType = DuckType.GENERAL,
        skills: list[str] | None = None,
    ):
        self.duck_id = duck_id
        self.name = name
        self.duck_type = duck_type
        self.skills = skills or []

        self._task_queue: asyncio.Queue[DuckTaskPayload] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    # ─── 生命周期 ────────────────────────────────────

    async def start(self):
        """启动工作协程并注册到 Registry"""
        if self._running:
            return

        registry = DuckRegistry.get_instance()
        await registry.initialize()

        info = DuckInfo(
            duck_id=self.duck_id,
            name=self.name,
            duck_type=self.duck_type,
            status=DuckStatus.ONLINE,
            skills=self.skills,
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            is_local=True,
        )
        await registry.register(info)

        self._running = True
        self._worker_task = asyncio.create_task(self._run_loop())
        logger.info(f"Local Duck started: {self.duck_id} ({self.name})")

    async def stop(self):
        """停止工作协程并从 Registry 注销"""
        if not self._running:
            return

        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        registry = DuckRegistry.get_instance()
        await registry.set_status(self.duck_id, DuckStatus.OFFLINE)
        logger.info(f"Local Duck stopped: {self.duck_id}")

    # ─── 任务接收（由调度器直接调用） ────────────────

    async def enqueue_task(self, payload: DuckTaskPayload):
        """调度器直接向本地 Duck 投递任务"""
        await self._task_queue.put(payload)

    # ─── 主循环 ──────────────────────────────────────

    async def _run_loop(self):
        """持续从队列取任务并执行"""
        while self._running:
            try:
                payload = await asyncio.wait_for(
                    self._task_queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                # 定期更新心跳
                registry = DuckRegistry.get_instance()
                await registry.heartbeat(self.duck_id)
                continue
            except asyncio.CancelledError:
                break

            await self._execute_task(payload)

    async def _execute_task(self, payload: DuckTaskPayload):
        """执行单个任务并回传结果"""
        from services.duck_task_scheduler import get_task_scheduler

        registry = DuckRegistry.get_instance()
        await registry.set_current_task(self.duck_id, payload.task_id)

        start_time = time.time()
        success = False
        output: Any = None
        error: Optional[str] = None

        try:
            output = await self._do_work(payload)
            success = True
        except Exception as e:
            error = str(e)
            logger.error(f"Local Duck {self.duck_id} task failed: {e}")

        duration = time.time() - start_time

        result = DuckResultPayload(
            task_id=payload.task_id,
            success=success,
            output=output,
            error=error,
            duration=duration,
        )

        scheduler = get_task_scheduler()
        await scheduler.handle_result(self.duck_id, result)

    async def _do_work(self, payload: DuckTaskPayload) -> Any:
        """
        实际执行任务逻辑。
        使用本地 AutonomousAgent 执行，使其拥有截图、终端、文件等全套工具。
        """
        try:
            from app_state import get_autonomous_agent
            agent = get_autonomous_agent()
            if agent is None:
                raise RuntimeError("AutonomousAgent not initialized")
            result = await asyncio.wait_for(
                agent.run(payload.description),
                timeout=float(payload.timeout),
            )
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(f"Local Duck task timed out after {payload.timeout}s")
        except Exception:
            # 降级：直接用 LLM 补全（无工具）
            try:
                from app_state import get_llm_client
                client = get_llm_client()
                if client is None:
                    raise RuntimeError("No LLM client available")
                prompt = self._build_prompt(payload)
                resp = await asyncio.wait_for(
                    client.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=float(payload.timeout),
                )
                content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
                return content
            except Exception as llm_err:
                raise RuntimeError(f"Local Duck fallback LLM failed: {llm_err}")

    def _build_prompt(self, payload: DuckTaskPayload) -> str:
        """根据任务构建 LLM 提示"""
        parts = [f"You are a specialized {self.duck_type.value} agent named {self.name}."]
        if self.skills:
            parts.append(f"Your skills: {', '.join(self.skills)}")
        parts.append(f"\nTask: {payload.description}")
        if payload.params:
            parts.append(f"Parameters: {payload.params}")
        return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Local Duck Manager — 管理所有本地 Duck 实例
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class LocalDuckManager:
    """管理所有本地 Duck 实例（单例）"""

    _instance: Optional["LocalDuckManager"] = None

    def __init__(self):
        self._workers: Dict[str, LocalDuckWorker] = {}

    @classmethod
    def get_instance(cls) -> "LocalDuckManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create_local_duck(
        self,
        name: str,
        duck_type: DuckType = DuckType.GENERAL,
        skills: list[str] | None = None,
    ) -> DuckInfo:
        """创建并启动一个新的本地 Duck"""
        duck_id = f"local_{uuid.uuid4().hex[:8]}"

        worker = LocalDuckWorker(
            duck_id=duck_id,
            name=name,
            duck_type=duck_type,
            skills=skills,
        )
        await worker.start()
        self._workers[duck_id] = worker

        registry = DuckRegistry.get_instance()
        info = await registry.get(duck_id)
        logger.info(f"Local Duck created: {duck_id}")
        return info  # type: ignore

    async def destroy_local_duck(self, duck_id: str) -> bool:
        """停止并删除一个本地 Duck"""
        worker = self._workers.pop(duck_id, None)
        if not worker:
            return False
        await worker.stop()

        registry = DuckRegistry.get_instance()
        await registry.unregister(duck_id)
        logger.info(f"Local Duck destroyed: {duck_id}")
        return True

    async def destroy_all(self):
        """停止所有本地 Duck"""
        for duck_id in list(self._workers.keys()):
            await self.destroy_local_duck(duck_id)

    def get_worker(self, duck_id: str) -> Optional[LocalDuckWorker]:
        return self._workers.get(duck_id)

    def list_local_ducks(self) -> list[str]:
        return list(self._workers.keys())

    @property
    def count(self) -> int:
        return len(self._workers)


def get_local_duck_manager() -> LocalDuckManager:
    return LocalDuckManager.get_instance()
