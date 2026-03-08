"""
Local Duck Worker — 本地 Duck 运行时

在同一进程中以 asyncio 任务运行的 Duck Agent。
每个 Local Duck 有独立的任务队列，通过内存直接与调度器通信，
无需 WebSocket。
"""
from __future__ import annotations
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
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        self.duck_id = duck_id
        self.name = name
        self.duck_type = duck_type
        self.skills = skills or []
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

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
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
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
        """执行单个任务，向监控面板广播实时步骤，并回传结果"""
        from services.duck_task_scheduler import get_task_scheduler
        from ws_handler import broadcast_monitor_event

        registry = DuckRegistry.get_instance()
        await registry.set_current_task(self.duck_id, payload.task_id)

        desc_preview = (payload.description or "")[:80]
        logger.info(f"[Local Duck] {self.duck_id} executing task {payload.task_id}: {desc_preview}...")

        # 获取委派来源 session（用于广播到正确的监控客户端）
        scheduler = get_task_scheduler()
        source_session = scheduler._task_sessions.get(
            payload.task_id, f"duck_{self.duck_id}"
        )

        start_time = time.time()
        success = False
        output: Any = None
        error: Optional[str] = None

        # 广播任务开始事件（带 Duck 身份）
        await broadcast_monitor_event(
            session_id=source_session,
            task_id=payload.task_id,
            event={
                "type": "task_start",
                "task": payload.description,
                "task_id": payload.task_id,
                "duck_name": self.name,
                "duck_type": self.duck_type.value,
            },
            task_type="duck",
            worker_type="local_duck",
            worker_id=self.duck_id,
        )

        try:
            output = await self._do_work_with_monitoring(payload, source_session)
            success = True
        except Exception as e:
            error = str(e)
            logger.error(f"Local Duck {self.duck_id} task failed: {e}")
            # 广播任务失败事件
            await broadcast_monitor_event(
                session_id=source_session,
                task_id=payload.task_id,
                event={
                    "type": "task_complete",
                    "task_id": payload.task_id,
                    "success": False,
                    "summary": f"执行失败: {error[:200]}",
                },
                task_type="duck",
                worker_type="local_duck",
                worker_id=self.duck_id,
            )

        duration = time.time() - start_time

        result = DuckResultPayload(
            task_id=payload.task_id,
            success=success,
            output=output,
            error=error,
            duration=duration,
        )

        await scheduler.handle_result(self.duck_id, result)

    def _create_duck_llm_client(self) -> Optional[Any]:
        """若分身配置了独立 LLM，创建 LLMClient"""
        if not all([self.llm_api_key, self.llm_base_url, self.llm_model]):
            return None
        try:
            from agent.llm_client import LLMClient, LLMConfig
            config = LLMConfig(
                provider="openai",
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
                model=self.llm_model,
            )
            return LLMClient(config)
        except Exception as e:
            logger.warning("Duck LLM client creation failed: %s", e)
            return None

    @staticmethod
    def _check_output_is_plan_not_result(output: Any) -> bool:
        """
        检测 agent.run() 的返回结果是否是未执行的 action plan，而非真实完成结果。
        当 LLM 输出 action plan JSON 但未实际执行时，summary 会包含这些 JSON 字符串。
        也检测自然语言形式的计划描述（未真正执行工具）。
        Returns True → 任务未真正完成，需标记失败。
        """
        if output is None:
            return True
        if not isinstance(output, str):
            return False
        stripped = output.strip()
        # 默认返回值，表明 task_complete chunk 从未出现
        if stripped in ("", "任务已结束"):
            return True

        import re

        # ── 正向完成信号检测：如果包含明确的完成/成功标志，直接视为已完成 ──
        completion_signals = [
            r'(?:✓|✅|√)',                                      # 完成标记符号
            r'(?:已保存|已创建|已生成|已写入|已完成)',            # 明确的完成动词
            r'(?:saved|written|created|generated)\s+(?:to|at)',  # 英文完成标记
            r'(?:文件|file)\s*(?:大小|size)',                    # 文件大小信息=实际产出
            r'(?:分辨率|resolution)',                            # 图片产出信息
        ]
        completion_score = sum(1 for p in completion_signals if re.search(p, stripped, re.IGNORECASE))
        if completion_score >= 1:
            return False  # 有明确完成信号，不是计划

        # 检查 output 是否包含 action plan JSON 结构
        # 用正则直接提取 action_type 的值（兼容嵌套 JSON）
        if '"action_type"' in stripped and '"reasoning"' in stripped:
            for m in re.finditer(r'"action_type"\s*:\s*"([^"]+)"', stripped):
                atype = m.group(1)
                if atype and atype != "finish":
                    # 找到非 finish 的 action plan → 任务未完成
                    return True
        # 检测自然语言形式的计划描述（LLM 只描述了要做什么，没实际执行）
        plan_indicators = [
            r'(?:任务|执行)\s*(?:分析|策略|规划|计划)',
            r'(?:我来|接下来|首先).*(?:分析|规划|创建|编写)',
            r'(?:需要|应该|将会|可以).*(?:创建|编写|实现|开发)',
        ]
        plan_score = sum(1 for p in plan_indicators if re.search(p, stripped))
        # 如果输出很短（<500字符）且包含多个计划指标词，很可能只是描述
        if len(stripped) < 500 and plan_score >= 2:
            return True
        return False

    async def _do_work_with_monitoring(self, payload: DuckTaskPayload, source_session: str) -> Any:
        """
        流式执行任务并将每一步广播到监控面板（带 Duck 身份标识）。
        替代原 _do_work，使 Duck 执行过程在"AI 监控中心"实时可见，包含完整 action 链路。
        """
        from ws_handler import broadcast_monitor_event
        from app_state import get_autonomous_agent, set_duck_context

        # 获取最新 Duck 配置（用户可能已更新 llm_config）
        registry = DuckRegistry.get_instance()
        duck = await registry.get(self.duck_id)
        if duck:
            self.llm_api_key = duck.llm_api_key
            self.llm_base_url = duck.llm_base_url
            self.llm_model = duck.llm_model

        duck_ctx = {
            "name": self.name,
            "duck_type": self.duck_type.value,
            "skills": self.skills,
        }
        set_duck_context(duck_ctx)
        override_llm = self._create_duck_llm_client()

        agent = get_autonomous_agent()
        if agent is None:
            raise RuntimeError("AutonomousAgent not initialized")

        # 使用 task_id 构建隔离的 duck session，避免与主 Agent session 状态混用
        duck_session = f"duck_{self.duck_id}_{payload.task_id[:6]}"

        # 活跃时间追踪（每个 chunk 到来时更新），用于惰性超时检测
        last_active: list = [time.time()]
        INACTIVITY_TIMEOUT = 90  # 90 秒无任何 chunk → 认为任务卡死

        # 获取 scheduler 引用，用于更新任务活跃时间
        from services.duck_task_scheduler import get_task_scheduler
        _scheduler = get_task_scheduler()

        async def _stream_run(description: str) -> str:
            """流式迭代 run_autonomous，广播每个 chunk，返回最终 summary"""
            old_llm = None
            if override_llm is not None:
                old_llm = agent.llm
                agent.llm = override_llm
            try:
                summary = ""
                async for chunk in agent.run_autonomous(description, session_id=duck_session):
                    last_active[0] = time.time()  # 有进展，更新活跃时间
                    _scheduler.update_task_activity(payload.task_id)  # 同步更新调度器层面的活跃时间
                    # 实时广播执行步骤到全局监控面板
                    await broadcast_monitor_event(
                        session_id=source_session,
                        task_id=payload.task_id,
                        event=chunk,
                        task_type="duck",
                        worker_type="local_duck",
                        worker_id=self.duck_id,
                    )
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "task_complete":
                        summary = chunk.get("summary", "") or ""
                        break
                    if chunk_type == "task_stopped":
                        raise RuntimeError(chunk.get("message", "任务被停止"))
                    if chunk_type == "error":
                        raise RuntimeError(chunk.get("error", "任务执行错误"))
                return summary or "任务已结束"
            finally:
                if old_llm is not None:
                    agent.llm = old_llm

        async def _run_smart(description: str, hard_timeout: float) -> str:
            """
            智能超时执行：
            - 每 20s 检查 Duck 是否仍活跃（有 chunk 产出）
            - 若 {INACTIVITY_TIMEOUT}s 内无任何 chunk → 判定 Duck 卡死，取消任务
            - 若超过 hard_timeout 硬上限 → 取消任务
            只要 Duck 持续工作（截图、调用工具等产出 chunk），就不会超时。
            """
            last_active[0] = time.time()
            hard_deadline = time.time() + hard_timeout
            stream_task = asyncio.ensure_future(_stream_run(description))
            try:
                while True:
                    done, _ = await asyncio.wait({stream_task}, timeout=20)
                    if stream_task in done:
                        try:
                            return stream_task.result()
                        except asyncio.CancelledError:
                            raise RuntimeError("任务被外部取消")
                    now = time.time()
                    inactivity = now - last_active[0]
                    if now >= hard_deadline:
                        stream_task.cancel()
                        await asyncio.gather(stream_task, return_exceptions=True)
                        raise asyncio.TimeoutError(
                            f"任务超时：总执行时间超过 {int(hard_timeout)}s 上限"
                        )
                    if inactivity > INACTIVITY_TIMEOUT:
                        stream_task.cancel()
                        await asyncio.gather(stream_task, return_exceptions=True)
                        raise asyncio.TimeoutError(
                            f"任务卡死：{int(inactivity)}s 内无任何进展，Duck 可能已挂起"
                        )
            finally:
                if not stream_task.done():
                    stream_task.cancel()
                    await asyncio.gather(stream_task, return_exceptions=True)

        try:
            result = await _run_smart(payload.description, float(payload.timeout))
            # 检测结果是否只是计划描述，而非真正执行结果
            if self._check_output_is_plan_not_result(result):
                logger.warning(
                    f"Duck {self.duck_id} returned plan instead of result, retrying with stronger prompt"
                )
                reinforced_desc = (
                    f"【强制执行模式】以下任务必须实际执行，不要只描述或规划。"
                    f"你必须使用 write_file、run_shell 等工具动作来完成任务。"
                    f"禁止只输出文字分析。\n\n"
                    f"原始任务：{payload.description}"
                )
                remaining_timeout = max(float(payload.timeout) * 0.7, 60.0)
                result = await _run_smart(reinforced_desc, remaining_timeout)
                if self._check_output_is_plan_not_result(result):
                    raise RuntimeError(
                        "任务未真正完成：Duck 返回了执行计划而非结果，可能是依赖缺失或脚本执行失败。"
                        f"请重新指派任务或让主 Agent 直接处理。"
                        f"（输出摘要：{str(result)[:150]}）"
                    )
            return result
        except asyncio.TimeoutError as e:
            raise RuntimeError(str(e))
        except Exception as e:
            logger.warning(f"Local Duck agent run failed, attempting LLM fallback: {e}")
            # 若任务涉及文件创建，LLM 无法真正写文件，不降级
            desc = (payload.description or "").lower()
            if any(k in desc for k in ("保存", "创建", "写入", "write", "create", ".html", ".md")):
                raise RuntimeError(
                    f"任务涉及文件创建，但 Agent 执行失败（{e}）。请重试或由主 Agent 直接处理。"
                )
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
        finally:
            set_duck_context(None)

    async def _do_work(self, payload: DuckTaskPayload) -> Any:
        """
        实际执行任务逻辑。
        使用本地 AutonomousAgent 执行，使其拥有截图、终端、文件等全套工具。
        注入 Duck 身份（name/duck_type/skills）到 prompt，使 Agent 知晓专项技能。
        若分身配置了独立 LLM（api_key/base_url/model），优先使用以更有效运用大模型。
        """
        from app_state import get_autonomous_agent, set_duck_context

        # 从 registry 获取最新配置（用户可能已更新 llm_config）
        registry = DuckRegistry.get_instance()
        duck = await registry.get(self.duck_id)
        if duck:
            self.llm_api_key = duck.llm_api_key
            self.llm_base_url = duck.llm_base_url
            self.llm_model = duck.llm_model

        duck_ctx = {
            "name": self.name,
            "duck_type": self.duck_type.value,
            "skills": self.skills,
        }
        set_duck_context(duck_ctx)
        override_llm = self._create_duck_llm_client()
        try:
            agent = get_autonomous_agent()
            if agent is None:
                raise RuntimeError("AutonomousAgent not initialized")

            # 首次执行
            result = await asyncio.wait_for(
                agent.run(payload.description, override_llm=override_llm),
                timeout=float(payload.timeout),
            )
            # 检测是否真正完成：若 summary 是 action plan JSON 而非结果，说明任务未完成
            if self._check_output_is_plan_not_result(result):
                # 重试一次：用更强的执行指令重新运行
                logger.warning(
                    f"Duck {self.duck_id} returned plan instead of result, retrying with stronger prompt"
                )
                reinforced_desc = (
                    f"【强制执行模式】以下任务必须实际执行，不要只描述或规划。"
                    f"你必须使用 write_file、run_shell 等工具动作来完成任务。"
                    f"禁止只输出文字分析。\n\n"
                    f"原始任务：{payload.description}"
                )
                remaining_timeout = max(
                    float(payload.timeout) * 0.7, 60.0
                )
                result = await asyncio.wait_for(
                    agent.run(reinforced_desc, override_llm=override_llm),
                    timeout=remaining_timeout,
                )
                if self._check_output_is_plan_not_result(result):
                    raise RuntimeError(
                        "任务未真正完成：Duck 返回了执行计划而非结果，可能是依赖缺失或脚本执行失败。"
                        f"请重新指派任务或让主 Agent 直接处理。"
                        f"（输出摘要：{str(result)[:150]}）"
                    )
            return result
        except asyncio.TimeoutError:
            raise RuntimeError(f"Local Duck task timed out after {payload.timeout}s")
        except Exception as e:
            logger.warning(f"Local Duck agent.run failed, attempting LLM fallback: {e}")
            # 若任务涉及文件创建，LLM 无法真正写文件，不降级
            desc = (payload.description or "").lower()
            if any(k in desc for k in ("保存", "创建", "写入", "write", "create", ".html", ".md")):
                raise RuntimeError(
                    f"任务涉及文件创建，但 Agent 执行失败（{e}）。请重试或由主 Agent 直接处理。"
                )
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
        finally:
            set_duck_context(None)

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
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
    ) -> DuckInfo:
        """创建并启动一个新的本地 Duck"""
        duck_id = f"local_{uuid.uuid4().hex[:8]}"

        worker = LocalDuckWorker(
            duck_id=duck_id,
            name=name,
            duck_type=duck_type,
            skills=skills,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
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

    async def start_local_duck(self, duck_id: str) -> Optional[DuckInfo]:
        """启动离线的本地 Duck（从 Registry 恢复，用于后端重启后）"""
        registry = DuckRegistry.get_instance()
        await registry.initialize()
        duck = await registry.get(duck_id)
        if not duck or not duck.is_local:
            return None
        if self.get_worker(duck_id):
            return duck  # 已在运行

        worker = LocalDuckWorker(
            duck_id=duck_id,
            name=duck.name,
            duck_type=duck.duck_type,
            skills=duck.skills or [],
            llm_api_key=duck.llm_api_key,
            llm_base_url=duck.llm_base_url,
            llm_model=duck.llm_model,
        )
        await worker.start()
        self._workers[duck_id] = worker
        return await registry.get(duck_id)

    def list_local_ducks(self) -> list[str]:
        return list(self._workers.keys())

    @property
    def count(self) -> int:
        return len(self._workers)


def get_local_duck_manager() -> LocalDuckManager:
    return LocalDuckManager.get_instance()
