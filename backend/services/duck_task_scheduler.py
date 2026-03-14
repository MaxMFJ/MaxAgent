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

# ─── 全局 Duck 完成钩子（由 ws_handler 注册，避免循环导入）──────────────────
# 签名：async def hook(session_id: str, task: DuckTask) -> None
_duck_complete_hooks: list[Callable] = []

def register_duck_complete_hook(hook: Callable) -> None:
    """注册 Duck 任务完成后的全局钩子（如 ws_handler 用于触发主 Agent 续步）"""
    if hook not in _duck_complete_hooks:
        _duck_complete_hooks.append(hook)


class DuckTaskScheduler:
    """Duck 任务调度引擎 (单例)"""

    _instance: Optional["DuckTaskScheduler"] = None

    def __init__(self):
        self._tasks: Dict[str, DuckTask] = {}
        self._callbacks: Dict[str, ResultCallback] = {}    # task_id → callback
        self._task_sessions: Dict[str, str] = {}           # task_id → source_session_id（委派来源会话，用于完成后主动通知）
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
        source_session_id: Optional[str] = None,
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
            if source_session_id:
                self._task_sessions[task.task_id] = source_session_id
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
            # 通知用户任务正在排队等待
            session_id = self._task_sessions.get(task.task_id)
            if session_id:
                type_hint = f"（类型: {duck_type.value}）" if duck_type else ""
                await self._notify_session_duck_progress(
                    session_id, task.task_id,
                    f"⏳ 当前没有可用的 Duck{type_hint}，任务已排队等待。Duck 上线后会自动分配执行。"
                )
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
        task.last_activity = time.time()
        task.status = TaskStatus.ASSIGNED
        self._persist_task(task)

        registry = DuckRegistry.get_instance()
        await registry.set_current_task(duck_id, task.task_id, busy_reason="assigned_task")

        # 向委派来源会话发送进度通知：Duck 已接手
        session_id = self._task_sessions.get(task.task_id)
        if session_id:
            duck_info = await registry.get(duck_id)
            duck_label = f"{duck_info.duck_type.value} Duck" if duck_info else duck_id
            original_desc = task.original_description or task.description or ""
            desc_preview = original_desc[:60]
            await self._notify_session_duck_progress(
                session_id, task.task_id,
                f"🦆 {duck_label} 已接手任务：{desc_preview}...\n正在执行中，请等待结果。"
            )

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

        # 启动超时计时（留出 120s 缓冲，避免与 worker 内部 smart-timeout 竞争）
        watcher_timeout = task.timeout + 120
        handle = asyncio.create_task(self._timeout_watcher(task.task_id, watcher_timeout))
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

        # ── 自动重试判断（在释放 Duck 之前决定，避免 UI 状态闪烁）──────────────────
        should_retry = not result.success and task.retry_count < task.max_retries

        # 更新 Duck 注册表
        registry = DuckRegistry.get_instance()
        if result.success:
            await registry.set_current_task(duck_id, None)   # 成功：释放 Duck
            await registry.increment_completed(duck_id)
        elif should_retry:
            await registry.increment_failed(duck_id)          # 重试：保持 BUSY，不释放
        else:
            await registry.set_current_task(duck_id, None)   # 最终失败：释放 Duck
            await registry.increment_failed(duck_id)

        # ── 工作流级自动重试 ──────────────────────────────────────────────────────
        if should_retry:
            session_id_for_retry = self._task_sessions.get(result.task_id)
            await self._auto_retry_task(task, result, duck_id, session_id_for_retry)
            logger.info(
                f"Task {task.task_id} scheduled for auto-retry "
                f"({task.retry_count}/{task.max_retries}), duck_id={duck_id}"
            )
            return  # 跳过 callback / notify，等待重试结果

        self._persist_task(task)

        # 聚合子任务结果
        if task.parent_task_id:
            await self._check_parent_completion(task.parent_task_id)

        # 触发回调（自主模式通过 Future 回调驱动续步）
        cb = self._callbacks.pop(result.task_id, None)
        has_callback = cb is not None
        if cb:
            try:
                await cb(task)
            except Exception as e:
                logger.error(f"Task callback error: {e}")

        # 委派来源会话：子 Duck 完成后主动通知用户（主 Agent 接入对话）
        # 有 callback 的任务由自主模式 Future 驱动续步，跳过 webhook 续步避免重复执行
        session_id = self._task_sessions.pop(result.task_id, None)
        if session_id and not has_callback:
            await self._notify_session_duck_complete(session_id, task, result)

        logger.info(f"Task {task.task_id} completed: success={result.success}")

    async def _auto_retry_task(
        self,
        task: DuckTask,
        result: DuckResultPayload,
        failed_duck_id: str,
        session_id: Optional[str],
    ):
        """
        调度器层面的工作流自动重试。
        - 每次用更具体的执行指令增强任务描述
        - 重新调度给同类型的可用 Duck
        - 最多重试 task.max_retries 次，耗尽后由主 Agent 接管
        """
        import os
        import glob
        # ── 检查前一次执行是否已经产出了目标文件 ──────────────────────────────
        # 如果上次执行虽然超时/失败但已经写入了文件，视为部分成功，不再重试
        prev_output = str(result.output or "")
        prev_files = self._extract_file_paths_from_output(prev_output)
        # 当 output 为空（如超时/异常）时，根据任务描述推断并检查常见输出位置
        if not prev_files and (task.description or ""):
            prev_files = self._find_likely_output_files(task)
        if prev_files:
            # 有实际产出文件存在，将任务标记为成功完成
            logger.info(
                f"Task {task.task_id} failed but output files exist: {prev_files}, "
                "treating as success (partial completion)"
            )
            task.output = prev_output
            task.error = None
            task.status = TaskStatus.COMPLETED
            self._persist_task(task)

            # 释放 Duck
            registry = DuckRegistry.get_instance()
            await registry.set_current_task(failed_duck_id, None)
            await registry.increment_completed(failed_duck_id)

            # 触发回调和通知
            cb = self._callbacks.pop(task.task_id, None)
            has_callback = cb is not None
            if cb:
                try:
                    await cb(task)
                except Exception as e:
                    logger.error(f"Task callback error (partial completion): {e}")

            sid = self._task_sessions.pop(task.task_id, None)
            if sid and not has_callback:
                fake_result = DuckResultPayload(
                    task_id=task.task_id, success=True,
                    output=prev_output, error=None,
                )
                await self._notify_session_duck_complete(sid, task, fake_result)
            return

        # 保存原始任务描述（仅第一次）
        if task.original_description is None:
            task.original_description = task.description

        # 记录本次失败
        task.retry_errors.append((task.error or "未知错误")[:400])
        task.retry_count += 1

        error_summary = " → ".join(task.retry_errors)

        if task.retry_count == 1:
            retry_instruction = (
                "【第1次自动重试】上次执行失败，请这次**立即使用工具直接操作**，"
                "不要先描述计划。必须使用 write_file 或 run_shell 完成任务。"
            )
        else:
            retry_instruction = (
                f"【第{task.retry_count}次自动重试】已多次失败，请彻底换一种方式：\n"
                "① run_shell 安装所需依赖（pip install xxx）；\n"
                "② write_file 把脚本写到 /tmp/retry_task.py；\n"
                "③ run_shell 执行脚本并确认输出文件存在。\n"
                "禁止再次只输出描述/分析，必须通过工具调用完成。"
            )

        enhanced_desc = (
            f"{retry_instruction}\n"
            f"历史失败原因：{error_summary[:300]}\n\n"
            f"原始任务：{task.original_description}"
        )

        # 重置任务状态（准备重新调度）
        task.status = TaskStatus.PENDING
        task.assigned_duck_id = None
        task.output = None
        task.error = None
        task.description = enhanced_desc
        task.assigned_at = None
        self._persist_task(task)

        # 保留 session_id 以供重试结果通知使用
        if session_id:
            self._task_sessions[task.task_id] = session_id

        logger.info(
            f"Auto-retry: task={task.task_id} attempt={task.retry_count}/{task.max_retries} "
            f"duck={failed_duck_id} session={session_id}"
        )

        # 第1次重试时：异步通知主 Agent（fire-and-forget，不阻塞重试流程）
        if task.retry_count == 1 and session_id:
            asyncio.create_task(
                self._notify_main_agent_retry(session_id, task, failed_duck_id, error_summary)
            )

        # 尝试选择其他可用 Duck 重试；无其他可用时回退到原 Duck
        registry = DuckRegistry.get_instance()
        # 获取失败 duck 的类型，用于找同类型的替代
        failed_duck_info = await registry.get(failed_duck_id)
        duck_type = failed_duck_info.duck_type if failed_duck_info else None
        candidates = await registry.list_available(duck_type)
        # 排除失败的 duck（如果有其他选择）
        alt_candidates = [d for d in candidates if d.duck_id != failed_duck_id]
        if alt_candidates:
            # 选负载最轻的替代 duck
            best = min(alt_candidates, key=lambda d: d.completed_tasks + d.failed_tasks)
            # 释放原 duck
            await registry.set_current_task(failed_duck_id, None)
            logger.info(f"Auto-retry: switching from duck {failed_duck_id} to {best.duck_id}")
            await self._assign_to_duck(task, best.duck_id)
        else:
            # 无替代 duck，继续使用原 duck（保持 BUSY）
            await self._assign_to_duck(task, failed_duck_id)

    async def _notify_main_agent_retry(
        self,
        session_id: str,
        task: "DuckTask",
        duck_id: str,
        error_summary: str,
    ):
        """
        第1次自动重试时通知主 Agent（信息性，不中断重试流程）。
        主 Agent 可继续等待，也可主动 delegate_duck 覆盖本次自动重试。
        """
        try:
            from connection_manager import connection_manager
            desc_preview = (task.original_description or task.description or "")[:80]
            notify_content = (
                f"[系统通知] 🔄 自动重试中（第{task.retry_count}次/共{task.max_retries}次）\n"
                f"Duck：{duck_id}\n"
                f"任务：{desc_preview}...\n"
                f"失败原因：{error_summary[:200]}\n"
                f"已用更强的执行指令自动重新委派，请等待结果。\n"
                f"如有更具体方案（如指定依赖版本、脚本路径），可直接 delegate_duck 重新委派以覆盖本次重试。"
            )
            msg = {
                "type": "duck_task_retry",
                "task_id": task.task_id,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "content": notify_content,
                "session_id": session_id,
            }
            await connection_manager.broadcast_to_session(session_id, msg)
        except Exception as e:
            logger.warning(f"[auto_retry] Failed to notify main agent: {e}")

    @staticmethod
    def _find_likely_output_files(task: "DuckTask") -> list:
        """
        当 output 为空（超时/异常）时，检查 Duck 的沙箱工作区及桌面是否已有产出文件。
        避免「任务已完成但超时导致重试」时重复创建已存在的文件。
        策略优先级：
          1. Duck 沙箱工作区（任意文件类型，15分钟内修改）
          2. 描述中引用路径的同目录 HTML
          3. 桌面直接子目录 HTML（向后兼容旧行为）
        """
        import os
        import time
        import glob as glob_module

        candidates: list = []
        cutoff = time.time() - 900  # 15 分钟内产出的文件

        # ── 优先：扫描 Duck 沙箱工作区 ─────────────────────────────
        # 沙箱目录命名可能含可读 label（如 "AI数据搜集_dtask_9a"），
        # 因此通过 _metadata.json 匹配 duck_id + task_id 进行定位。
        duck_id = task.assigned_duck_id or ""
        task_prefix = (task.task_id or "")[:8]
        if duck_id and task_prefix:
            sandbox_root = os.path.expanduser("~/Desktop/macagent_workspace/ducks")
            if os.path.isdir(sandbox_root):
                # 遍历子目录找到匹配任务的 workspace
                for entry in os.scandir(sandbox_root):
                    if not entry.is_dir():
                        continue
                    meta_file = os.path.join(entry.path, "_metadata.json")
                    if not os.path.exists(meta_file):
                        # 降级：尝试旧格式目录名 {duck_id}_{task_prefix}
                        if entry.name == f"{duck_id}_{task_prefix}":
                            workspace = os.path.join(entry.path, "workspace")
                        else:
                            continue
                    else:
                        try:
                            import json as _json
                            meta = _json.loads(open(meta_file, encoding="utf-8").read())
                            if meta.get("duck_id") != duck_id or not meta.get("task_id", "").startswith(task_prefix):
                                continue
                        except Exception:
                            continue
                        workspace = os.path.join(entry.path, "workspace")
                    if not os.path.isdir(workspace):
                        continue
                    # 递归扫描所有文件，不限扩展名
                    for dirpath, _dirs, files in os.walk(workspace):
                        for fname in files:
                            if fname.startswith("."):
                                continue
                            fpath = os.path.join(dirpath, fname)
                            try:
                                if os.path.isfile(fpath) and os.path.getmtime(fpath) >= cutoff:
                                    candidates.append(fpath)
                            except OSError:
                                pass
                    if candidates:
                        seen: set = set()
                        return [p for p in candidates if p not in seen and not seen.add(p)]

        # ── 回退：从描述中提取参考路径，检查同目录下是否有 .html 产出 ─────
        import re
        raw_desc = task.original_description or task.description or ""
        desc = raw_desc.lower()
        # 仅在有文件输出类关键词时才做桌面/路径扫描
        if not desc or not any(k in desc for k in ("网页", "html", "设计", "design", "创建", "create", "保存", "save")):
            return []

        ref_paths = re.findall(
            r'(/(?:Users|tmp|var|home)/[^\s"\'\\,，；；、\]\)>]+\.(?:html?|png|jpg|jpeg|md|txt))',
            raw_desc,
            re.IGNORECASE,
        )
        for p in ref_paths:
            if os.path.exists(p):
                base_dir = os.path.dirname(p)
                for f in glob_module.glob(os.path.join(base_dir, "*.html")) + glob_module.glob(os.path.join(base_dir, "*.htm")):
                    if os.path.isfile(f):
                        candidates.append(f)

        # 检查 Desktop 下最近 15 分钟内修改的 .html
        desktop = os.path.expanduser("~/Desktop")
        if os.path.isdir(desktop):
            for p in glob_module.glob(os.path.join(desktop, "*.html")) + glob_module.glob(os.path.join(desktop, "*.htm")):
                try:
                    if os.path.isfile(p) and os.path.getmtime(p) >= cutoff:
                        candidates.append(p)
                except OSError:
                    pass

        seen2: set = set()
        return [p for p in candidates if p not in seen2 and not seen2.add(p)]

    @staticmethod
    def _extract_file_paths_from_output(output: any) -> list:
        """
        从 Duck 输出中提取文件路径列表。
        扫描字符串中绝对路径（/Users/、/tmp/ 等），兼容 dict/str 输出。
        """
        import re
        text = ""
        if isinstance(output, str):
            text = output
        elif isinstance(output, dict):
            import json
            try:
                text = json.dumps(output, ensure_ascii=False)
            except Exception:
                text = str(output)
        elif output is not None:
            text = str(output)

        # 匹配绝对路径，支持常见文件扩展名
        pattern = r'(/(?:Users|tmp|var|home)/[^\s"\'\\,，；；、\]\)>]+\.(?:html?|py|md|txt|json|png|jpg|jpeg|gif|webp|pdf|csv|js|ts|css|sh|yaml|yml|xml|zip))'
        paths = re.findall(pattern, text, re.IGNORECASE)
        # 去重 + 校验文件真实存在（避免误报 action plan 中「计划」路径）
        import os
        seen: set = set()
        result = []
        for p in paths:
            if p not in seen and os.path.exists(p):
                seen.add(p)
                result.append(p)
        return result

    async def _notify_session_duck_progress(
        self, session_id: str, task_id: str, content: str
    ):
        """向委派来源会话发送 Duck 执行进度消息（展示在 Chat 中）"""
        try:
            from connection_manager import connection_manager
            msg = {
                "type": "duck_task_progress",
                "task_id": task_id,
                "content": content,
                "session_id": session_id,
            }
            await connection_manager.broadcast_to_session(session_id, msg)
        except Exception as e:
            logger.debug(f"Failed to send duck progress: {e}")

    async def _notify_session_duck_complete(
        self, session_id: str, task: DuckTask, result: DuckResultPayload
    ):
        """
        子 Duck 完成后，向委派来源会话广播 duck_task_complete，主 Agent 主动联系用户。
        同时将结果写入对话上下文，便于后续对话引用。
        Duck 创建的文件路径自动注入主 session 的 created_files，确保后续对话系统提示包含路径。
        """
        try:
            from connection_manager import connection_manager
            from agent.context_manager import context_manager

            registry = DuckRegistry.get_instance()
            duck_label = "Duck"
            if task.assigned_duck_id:
                duck_info = await registry.get(task.assigned_duck_id)
                if duck_info:
                    duck_label = f"{duck_info.duck_type.value} Duck"

            # 优先使用原始任务描述（避免展示 retry 增强描述）
            original_desc = task.original_description or task.description or ""
            desc_preview = original_desc[:80]
            if len(original_desc) > 80:
                desc_preview += "..."

            ctx_mgr = context_manager.get_or_create(session_id)

            if result.success:
                output_str = str(task.output) if task.output is not None else ""
                # 提取 Duck 创建的文件路径，注入主 session created_files（让系统提示携带路径）
                created_paths = self._extract_file_paths_from_output(task.output)
                for p in created_paths:
                    ctx_mgr.add_created_file(p)
                    logger.info(f"Duck task: registered created file to session {session_id}: {p}")

                # 将 Duck 产出写入工作区（供后续 Duck/主 Agent 引用）
                ctx_mgr.add_duck_output(
                    task_id=task.task_id,
                    duck_type=duck_label,
                    duck_id=task.assigned_duck_id or "",
                    description_preview=desc_preview,
                    file_paths=created_paths,
                    summary=output_str[:300],
                )

                # 构建通知内容，优先显示文件路径
                if created_paths:
                    paths_hint = "\n".join(f"- `{p}`" for p in created_paths)
                    output_display = (
                        f"已创建以下文件：\n{paths_hint}\n\n"
                        + (output_str[:800] + "...[已截断]" if len(output_str) > 800 else output_str)
                    )
                else:
                    output_display = output_str[:1000] + ("...[已截断]" if len(output_str) > 1000 else "")

                content = (
                    f"{duck_label} 已完成任务：{desc_preview}\n\n"
                    f"**执行结果：**\n{output_display}"
                )
            else:
                retry_hint = ""
                if task.retry_count > 0:
                    retry_hint = f"（已自动重试 {task.retry_count} 次）"
                content = (
                    f"{duck_label} 任务失败{retry_hint}：{desc_preview}\n\n"
                    f"**错误信息：** {task.error or '未知错误'}\n\n"
                    f"**建议处理方式：**\n"
                    f"- Duck 已多次尝试仍失败，请**自己使用工具**直接完成此任务\n"
                    f"- 对于 HTML/代码文件：直接用 `write_file` 创建，无需依赖外部库\n"
                    f"- 原始任务：{original_desc[:200]}"
                )

            msg = {
                "type": "duck_task_complete",
                "task_id": task.task_id,
                "success": result.success,
                "content": content,
                "session_id": session_id,
                "duck_id": task.assigned_duck_id,
            }

            await connection_manager.broadcast_to_session(session_id, msg)

            # 写入对话上下文，便于后续对话引用
            ctx_mgr.add_message("assistant", content)
            # 持久化到磁盘（data/contexts/{session_id}.json），避免重启后端后 Duck 结果丢失
            context_manager.save_session(session_id)

            # 触发全局 Duck 完成钩子（如 ws_handler 自动续步逻辑）
            for hook in _duck_complete_hooks:
                try:
                    await hook(session_id, task)
                except Exception as _hook_err:
                    logger.warning(f"duck_complete_hook error: {_hook_err}")
        except Exception as e:
            logger.warning(f"Failed to notify session for duck task complete: {e}")

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

        # 委派来源会话：任务失败时也主动通知用户
        session_id = self._task_sessions.pop(task.task_id, None)
        if session_id:
            result = DuckResultPayload(
                task_id=task.task_id,
                success=False,
                output=None,
                error=error,
                duration=0,
            )
            await self._notify_session_duck_complete(session_id, task, result)

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

    def update_task_activity(self, task_id: str) -> None:
        """更新任务最后活跃时间（由 worker 在每个 chunk 产出时调用）"""
        task = self._tasks.get(task_id)
        if task and task.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING):
            task.last_activity = time.time()

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
