"""
Duck Task DAG — 有向无环图任务编排

支持将复杂任务拆解为子任务 DAG:
- 节点: 子任务 (DuckTask)
- 边: 依赖关系 (A 完成后才能启动 B)
- 并行执行无依赖关系的子任务
- A Duck 的结果可作为 B Duck 的输入
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from services.duck_protocol import DuckTask, DuckType, TaskStatus

logger = logging.getLogger(__name__)

# DAG 回调
DAGCallback = Callable[["DAGExecution"], Coroutine[Any, Any, None]]


@dataclass
class DAGNode:
    """DAG 中的一个子任务节点"""
    node_id: str
    description: str
    task_type: str = "general"
    params: Dict[str, Any] = field(default_factory=dict)
    duck_type: Optional[DuckType] = None
    duck_id: Optional[str] = None           # 指定 Duck
    timeout: int = 600
    priority: int = 0

    # DAG 关系
    depends_on: List[str] = field(default_factory=list)  # 依赖的 node_id 列表
    input_mapping: Dict[str, str] = field(default_factory=dict)
    # 例: {"data": "node_a"} 表示将 node_a 的 output 作为本节点 params["data"]

    # 运行时状态
    task_id: Optional[str] = None           # 对应的 DuckTask ID
    status: TaskStatus = TaskStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    remaining_deps: int = 0                 # Pull-model: 剩余未完成依赖数
    execution_emitted: bool = False           # Replay protection: 已入队标志

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "description": self.description,
            "task_type": self.task_type,
            "params": self.params,
            "duck_type": self.duck_type.value if self.duck_type else None,
            "duck_id": self.duck_id,
            "timeout": self.timeout,
            "depends_on": self.depends_on,
            "input_mapping": self.input_mapping,
            "status": self.status.value,
            "task_id": self.task_id,
            "output": self.output,
            "error": self.error,
        }


@dataclass
class DAGExecution:
    """一次 DAG 执行实例"""
    dag_id: str
    description: str
    session_id: str = ""              # 关联的用户 session
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    status: str = "pending"   # pending / running / completed / failed / cancelled
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    output: Any = None        # 聚合后的最终结果
    error: Optional[str] = None
    group_id: Optional[str] = None    # 关联的 GroupChat ID

    def to_dict(self) -> dict:
        return {
            "dag_id": self.dag_id,
            "description": self.description,
            "session_id": self.session_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
            "group_id": self.group_id,
        }


import threading as _threading

class DAGTaskOrchestrator:
    """DAG 任务编排器（单例）"""

    _instance: Optional["DAGTaskOrchestrator"] = None
    _instance_lock = _threading.Lock()
    _complete_hooks: List[Callable] = []  # 全局完成钩子

    def __init__(self):
        self._executions: Dict[str, DAGExecution] = {}
        self._task_to_dag: Dict[str, tuple[str, str]] = {}  # task_id → (dag_id, node_id)
        self._callbacks: Dict[str, DAGCallback] = {}
        self._dag_locks: Dict[str, asyncio.Lock] = {}  # per-DAG lock for _on_node_complete
        self._execution_ttl: int = 1800  # 已完成 DAG 保留 30 分钟

    @classmethod
    def get_instance(cls) -> "DAGTaskOrchestrator":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def register_complete_hook(cls, hook: Callable):
        """注册全局 DAG 完成钩子（类似 duck_complete_hook）"""
        cls._complete_hooks.append(hook)

    # ─── 创建 DAG ────────────────────────────────────

    def create_dag(
        self,
        description: str,
        nodes: List[DAGNode],
        callback: Optional[DAGCallback] = None,
        session_id: str = "",
        existing_group_id: Optional[str] = None,
    ) -> DAGExecution:
        """
        创建一个 DAG 执行实例。
        nodes 列表中的 depends_on 字段定义依赖关系。
        existing_group_id: 若指定，则使用已有群聊而不新建。
        """
        dag_id = f"dag_{uuid.uuid4().hex[:8]}"

        # 验证 DAG 结构
        node_ids = {n.node_id for n in nodes}
        for node in nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    raise ValueError(f"Node '{node.node_id}' depends on unknown node '{dep}'")

        # 检测循环依赖
        if self._has_cycle(nodes):
            raise ValueError("DAG contains circular dependencies")

        execution = DAGExecution(
            dag_id=dag_id,
            description=description,
            session_id=session_id,
            nodes={n.node_id: n for n in nodes},
            group_id=existing_group_id or None,
        )

        # 初始化每个节点的 remaining_deps 计数器
        for node in execution.nodes.values():
            node.remaining_deps = len(node.depends_on)

        self._executions[dag_id] = execution
        self._dag_locks[dag_id] = asyncio.Lock()
        if callback:
            self._callbacks[dag_id] = callback

        logger.info(f"DAG created: {dag_id} with {len(nodes)} nodes")

        # Journal: DAG_CREATED (sync context → fire-and-forget)
        try:
            from services.runtime_journal import get_journal, DAG_CREATED
            asyncio.get_event_loop().create_task(
                get_journal().append(DAG_CREATED, dag_id=dag_id,
                                     extra={"node_count": len(nodes)})
            )
        except Exception:
            pass

        return execution

    # ─── 执行 DAG ────────────────────────────────────

    async def execute(self, dag_id: str):
        """执行 DAG：按依赖顺序分发任务"""
        execution = self._executions.get(dag_id)
        if not execution:
            raise ValueError(f"DAG not found: {dag_id}")

        try:
            from services.duck_task_scheduler import get_task_scheduler
            await get_task_scheduler().initialize()
        except Exception as e:
            logger.warning(f"DAG {dag_id} scheduler init failed: {e}")

        # v2.3: Adaptive backpressure — reject under high pressure
        try:
            from services.duck_ready_queues import is_system_overloaded, compute_pressure_score
            if is_system_overloaded():
                pressure = compute_pressure_score()
                logger.warning(
                    f"[pressure_throttle] DAG {dag_id} rejected: "
                    f"pressure={pressure:.2f} > threshold"
                )
                execution.status = "rejected"
                execution.error = f"RETRY_LATER: system pressure {pressure:.2f}"
                return
        except Exception:
            pass

        execution.status = "running"
        logger.info(f"DAG executing: {dag_id}")

        # 群聊：复用已有群聊或新建
        if execution.session_id:
            if execution.group_id:
                await self._reuse_group_chat(execution)
            else:
                await self._create_group_chat(execution)

        # Pull-model: 将根节点（无依赖）直接入队 ready queue
        await self._enqueue_root_nodes(execution)

        # Fallback: _schedule_ready_nodes 处理未被 pull 覆盖的节点
        await self._schedule_ready_nodes(execution)

    async def _enqueue_root_nodes(self, execution: DAGExecution):
        """将无依赖的根节点入队 ready queue（Pull-model 主路径）"""
        from services.duck_ready_queues import enqueue_ready_node

        # 统计根节点数量，辅助诊断串行任务被误判为并行的问题
        root_nodes = [
            n for n in execution.nodes.values()
            if n.status == TaskStatus.PENDING and n.remaining_deps == 0 and not n.execution_emitted
        ]
        if len(root_nodes) > 1:
            root_ids = [n.node_id for n in root_nodes]
            logger.warning(
                f"DAG {execution.dag_id}: found {len(root_nodes)} root nodes "
                f"({root_ids}). If this is a serial DAG, dependencies may be misconfigured."
            )

        for node in root_nodes:

            params = dict(node.params)
            dag_id = execution.dag_id
            node_id = node.node_id

            async def on_complete(task: DuckTask, _dag_id=dag_id, _nid=node_id):
                await self._on_node_complete(_dag_id, _nid, task)

            accepted = await enqueue_ready_node(
                dag_id=execution.dag_id,
                node_id=node.node_id,
                description=node.description,
                task_type=node.task_type,
                params=params,
                priority=node.priority,
                timeout=node.timeout,
                duck_type=node.duck_type,
                duck_id=node.duck_id,
                callback=on_complete,
                session_id=execution.session_id,
            )
            if accepted:
                node.execution_emitted = True
                node.status = TaskStatus.ENQUEUED

    async def _schedule_ready_nodes(self, execution: DAGExecution):
        """找出所有可以开始的节点并提交"""
        from services.duck_task_scheduler import get_task_scheduler

        scheduler = get_task_scheduler()

        for node in execution.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            if node.execution_emitted:
                continue
            # Double-check remaining_deps（与 deps_satisfied 互为校验）
            if node.remaining_deps > 0:
                continue

            # 检查所有依赖是否完成
            deps_satisfied = all(
                execution.nodes[dep].status == TaskStatus.COMPLETED
                for dep in node.depends_on
            )
            if not deps_satisfied:
                continue

            # 注入依赖节点的输出到当前节点参数
            params = dict(node.params)
            for param_key, source_node_id in node.input_mapping.items():
                source_node = execution.nodes.get(source_node_id)
                if source_node and source_node.output is not None:
                    params[param_key] = source_node.output

            # 确定调度策略
            strategy = "direct" if node.duck_id else "single"

            # 创建回调以跟踪完成
            dag_id = execution.dag_id
            node_id = node.node_id

            async def on_complete(task: DuckTask, _dag_id=dag_id, _node_id=node_id):
                await self._on_node_complete(_dag_id, _node_id, task)

            task = await scheduler.submit(
                description=node.description,
                task_type=node.task_type,
                params=params,
                priority=node.priority,
                timeout=node.timeout,
                strategy=strategy,
                target_duck_id=node.duck_id,
                target_duck_type=node.duck_type,
                callback=on_complete,
            )

            node.task_id = task.task_id
            node.status = TaskStatus.ASSIGNED
            node.execution_emitted = True  # 防止重复派发
            self._task_to_dag[task.task_id] = (execution.dag_id, node.node_id)

            logger.info(f"DAG {execution.dag_id}: node {node.node_id} → task {task.task_id} (via fallback scheduler)")

            # 群聊: 主 Agent 发布任务分配消息
            await self._group_post_task_assign(execution, node)

    async def _on_node_complete(self, dag_id: str, node_id: str, task: DuckTask):
        """节点任务完成回调 — Pull-model: 递减子节点计数器并入队就绪节点

        使用 per-DAG 锁防止多个节点同时完成时的并发竞争（例如菱形 DAG 中
        B 和 C 同时完成时修改 D 的 remaining_deps）。
        """
        lock = self._dag_locks.get(dag_id)
        if not lock:
            lock = asyncio.Lock()
            self._dag_locks[dag_id] = lock

        async with lock:
            execution = self._executions.get(dag_id)
            if not execution:
                return

            node = execution.nodes.get(node_id)
            if not node:
                return

            # Idempotent guard: 防止同一节点回调被触发多次
            if node.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                logger.info(
                    f"DAG {dag_id}: node {node_id} already in terminal state "
                    f"{node.status.value}, ignoring duplicate callback"
                )
                return

            node.status = task.status
            node.output = task.output
            node.error = task.error

            logger.info(f"DAG {dag_id}: node {node_id} → {task.status.value}")

            # 群聊: Duck 汇报完成/失败
            await self._group_post_node_result(execution, node, task)

            if task.status == TaskStatus.FAILED:
                self._propagate_failure(execution, node_id)
            elif task.status == TaskStatus.COMPLETED:
                # Pull-model: 递减依赖此节点的子节点计数器
                await self._decrement_and_enqueue(execution, node_id)

            # Fallback: 仍调用 _schedule_ready_nodes 处理未被 pull 覆盖的节点
            await self._schedule_ready_nodes(execution)

            # 检查 DAG 是否全部完成
            await self._check_dag_completion(execution)

    async def _decrement_and_enqueue(self, execution: DAGExecution, completed_node_id: str):
        """递减子节点的 remaining_deps，为零时入队 ready queue"""
        from services.duck_ready_queues import enqueue_ready_node

        for child in execution.nodes.values():
            if completed_node_id not in child.depends_on:
                continue
            if child.status != TaskStatus.PENDING:
                continue

            child.remaining_deps = max(0, child.remaining_deps - 1)

            if child.remaining_deps == 0:
                # Replay protection: 防止 crash recovery 重复入队
                if child.execution_emitted:
                    logger.info(
                        f"DAG {execution.dag_id}: node {child.node_id} "
                        f"already emitted, skipping (replay protection)"
                    )
                    continue

                # 注入依赖节点的输出
                params = dict(child.params)
                for param_key, source_node_id in child.input_mapping.items():
                    source_node = execution.nodes.get(source_node_id)
                    if source_node and source_node.output is not None:
                        params[param_key] = source_node.output

                dag_id = execution.dag_id
                child_node_id = child.node_id

                async def on_complete(task: DuckTask, _dag_id=dag_id, _nid=child_node_id):
                    await self._on_node_complete(_dag_id, _nid, task)

                accepted = await enqueue_ready_node(
                    dag_id=execution.dag_id,
                    node_id=child.node_id,
                    description=child.description,
                    task_type=child.task_type,
                    params=params,
                    priority=child.priority,
                    timeout=child.timeout,
                    duck_type=child.duck_type,
                    duck_id=child.duck_id,
                    callback=on_complete,
                    session_id=execution.session_id,
                )
                if accepted:
                    child.execution_emitted = True
                    child.status = TaskStatus.ENQUEUED
                    logger.info(
                        f"DAG {execution.dag_id}: node {child.node_id} deps satisfied, "
                        f"enqueued to pull queue"
                    )

    def _propagate_failure(self, execution: DAGExecution, failed_node_id: str):
        """传播失败：依赖失败节点的所有下游节点标记为失败"""
        for node in execution.nodes.values():
            if node.status == TaskStatus.PENDING and failed_node_id in node.depends_on:
                node.status = TaskStatus.FAILED
                node.error = f"Dependency '{failed_node_id}' failed"
                # 继续传播
                self._propagate_failure(execution, node.node_id)

    async def _check_dag_completion(self, execution: DAGExecution):
        """检查 DAG 是否全部完成"""
        all_nodes = list(execution.nodes.values())
        pending = [
            n for n in all_nodes
            if n.status in (TaskStatus.PENDING, TaskStatus.ENQUEUED, TaskStatus.ASSIGNED, TaskStatus.RUNNING)
        ]

        if pending:
            return  # 还有节点在执行或等待

        # 所有节点完成
        completed = [n for n in all_nodes if n.status == TaskStatus.COMPLETED]
        failed = [n for n in all_nodes if n.status == TaskStatus.FAILED]

        execution.completed_at = time.time()

        terminal_nodes = self._find_terminal_nodes(execution)

        if failed:
            execution.status = "failed"
            execution.error = f"{len(failed)} of {len(all_nodes)} nodes failed"
            execution.output = {
                "total_nodes": len(all_nodes),
                "completed": len(completed),
                "failed": len(failed),
                "results": {
                    n.node_id: {"output": n.output, "description": n.description}
                    for n in terminal_nodes if n.status == TaskStatus.COMPLETED
                },
                "errors": {
                    n.node_id: {"error": n.error, "description": n.description}
                    for n in failed
                }
            }
        else:
            execution.status = "completed"
            execution.output = {
                "total_nodes": len(all_nodes),
                "completed": len(completed),
                "failed": len(failed),
                "results": {
                    n.node_id: {"output": n.output, "description": n.description}
                    for n in terminal_nodes if n.status == TaskStatus.COMPLETED
                },
            }

        logger.info(f"DAG {execution.dag_id} finished: {execution.status}")

        # 清理 per-DAG 锁
        self._dag_locks.pop(execution.dag_id, None)

        # Journal: DAG_COMPLETED
        try:
            from services.runtime_journal import get_journal, DAG_COMPLETED
            await get_journal().append(DAG_COMPLETED, dag_id=execution.dag_id,
                                       extra={"status": execution.status})
        except Exception:
            pass

        # v2.3: Slow DAG detection
        dag_exec_time = execution.completed_at - execution.created_at
        try:
            from services.runtime_metrics import metrics as rt_m
            is_slow = rt_m.record_dag_exec_time(dag_exec_time)
            if is_slow:
                logger.warning(
                    f"[slow_dag_detected] DAG {execution.dag_id} "
                    f"exec_time={dag_exec_time:.1f}s exceeds p95*3 threshold"
                )
        except Exception:
            pass

        # 群聊: 更新状态并发布总结
        await self._group_finalize(execution)

        # 触发回调
        cb = self._callbacks.pop(execution.dag_id, None)
        if cb:
            try:
                await cb(execution)
            except Exception as e:
                logger.error(f"DAG callback error: {e}")

        # 触发全局完成钩子（供 ws_handler chat 续步使用）
        for hook in self._complete_hooks:
            try:
                await hook(execution)
            except Exception as e:
                logger.error(f"DAG complete hook error: {e}")

        # 延迟清理 DAG 执行记录，防止内存泄漏
        self._schedule_dag_cleanup(execution.dag_id)

    def _schedule_dag_cleanup(self, dag_id: str):
        """延迟清理已完成的 DAG 执行记录"""
        async def _do_cleanup():
            await asyncio.sleep(self._execution_ttl)
            execution = self._executions.pop(dag_id, None)
            if execution:
                # 清理 task_to_dag 中关联的条目
                task_ids = [tid for tid, (did, _) in self._task_to_dag.items() if did == dag_id]
                for tid in task_ids:
                    self._task_to_dag.pop(tid, None)
                logger.info(f"[dag_cleanup] Removed DAG {dag_id} ({len(task_ids)} task mappings)")

        asyncio.create_task(_do_cleanup())

    def _find_terminal_nodes(self, execution: DAGExecution) -> List[DAGNode]:
        """找到终端节点（没有其他节点依赖它的节点）"""
        depended_on: Set[str] = set()
        for node in execution.nodes.values():
            depended_on.update(node.depends_on)
        return [n for n in execution.nodes.values() if n.node_id not in depended_on]

    # ─── 取消 DAG ────────────────────────────────────

    async def cancel(self, dag_id: str) -> bool:
        """取消整个 DAG 执行"""
        execution = self._executions.get(dag_id)
        if not execution or execution.status in ("completed", "failed", "cancelled"):
            return False

        from services.duck_task_scheduler import get_task_scheduler
        scheduler = get_task_scheduler()

        for node in execution.nodes.values():
            if node.task_id and node.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING):
                await scheduler.cancel(node.task_id)
            if node.status == TaskStatus.PENDING:
                node.status = TaskStatus.CANCELLED

        execution.status = "cancelled"
        execution.completed_at = time.time()
        self._dag_locks.pop(dag_id, None)

        # 项目经理: 清理监控数据
        try:
            from services.task_monitor_bot import TaskMonitorBot
            TaskMonitorBot.cleanup(dag_id)
        except Exception:
            pass

        # 群聊: 取消
        if execution.group_id:
            try:
                from services.group_chat_service import get_group_chat_service
                await get_group_chat_service().cancel_group(execution.group_id)
            except Exception:
                pass

        logger.info(f"DAG cancelled: {dag_id}")
        # 延迟清理取消的 DAG
        self._schedule_dag_cleanup(dag_id)
        return True

    # ─── 查询 ────────────────────────────────────────

    def get_execution(self, dag_id: str) -> Optional[DAGExecution]:
        return self._executions.get(dag_id)

    def list_executions(self, status: Optional[str] = None) -> List[DAGExecution]:
        execs = list(self._executions.values())
        if status:
            execs = [e for e in execs if e.status == status]
        execs.sort(key=lambda e: e.created_at, reverse=True)
        return execs

    # ─── Group Chat 集成 ─────────────────────────────

    async def _create_group_chat(self, execution: DAGExecution) -> None:
        """DAG 开始时自动创建群聊

        分两阶段：
        1. 核心创建 — 必须成功（失败则 ERROR 日志 + group_id 保持 None）
        2. 装饰（监控 bot / 执行计划）— 失败仅 WARNING，不影响后续群聊消息
        """
        # ── Phase 1: 核心创建 ──
        try:
            from services.group_chat_service import get_group_chat_service
            svc = get_group_chat_service()
            gc = await svc.create_group(
                session_id=execution.session_id,
                title=execution.description,
                dag_id=execution.dag_id,
            )
            execution.group_id = gc.group_id
            logger.info("群聊已创建: %s dag=%s", gc.group_id, execution.dag_id)
        except Exception as e:
            logger.error("创建群聊失败（核心阶段）: %s", e, exc_info=True)
            return

        # ── Phase 2: 装饰（监控 bot + 执行计划），失败不影响 group_id ──
        try:
            from services.task_monitor_bot import (
                TaskMonitorBot, MONITOR_BOT_ID, MONITOR_BOT_NAME, MONITOR_BOT_EMOJI,
            )
            from models.group_chat import GroupParticipant, ParticipantRole
            gc.add_participant(GroupParticipant(
                participant_id=MONITOR_BOT_ID,
                name=MONITOR_BOT_NAME,
                role=ParticipantRole.MONITOR,
                emoji=MONITOR_BOT_EMOJI,
            ))
            svc._save_group(gc)
            TaskMonitorBot.register(
                execution.dag_id, gc.group_id,
                execution.description, len(execution.nodes),
            )
            await svc.post_system_message(
                gc.group_id,
                f"{MONITOR_BOT_EMOJI} {MONITOR_BOT_NAME} 已加入，将在任务结束后发布执行分析报告",
            )
        except Exception as e:
            logger.warning("群聊监控 bot 注册失败: %s", e)

        try:
            node_list = "\n".join(
                f"  {i+1}. {n.description}"
                + (f" (依赖: {', '.join(n.depends_on)})" if n.depends_on else "")
                for i, n in enumerate(execution.nodes.values())
            )
            from models.group_chat import GroupMessageType
            await svc.post_message(
                gc.group_id, "main",
                f"📋 执行计划已生成，共 {len(execution.nodes)} 个子任务:\n{node_list}",
                msg_type=GroupMessageType.PLAN,
                metadata={"total_nodes": len(execution.nodes)},
            )
            await svc.update_task_panel(
                gc.group_id,
                total=len(execution.nodes), completed=0, failed=0,
                running=0, pending=len(execution.nodes),
            )
        except Exception as e:
            logger.warning("群聊执行计划发布失败: %s", e)

    async def _reuse_group_chat(self, execution: DAGExecution) -> None:
        """复用已有群聊，在其中追加新执行计划"""
        try:
            from services.group_chat_service import get_group_chat_service
            from models.group_chat import GroupChatStatus, GroupMessageType
            svc = get_group_chat_service()
            gc = await svc.get_group(execution.group_id)
            if not gc:
                logger.warning("续接群聊不存在: %s，改为新建", execution.group_id)
                execution.group_id = None
                await self._create_group_chat(execution)
                return

            # 若群聊已关闭状态，重新激活
            if gc.status != GroupChatStatus.ACTIVE:
                gc.status = GroupChatStatus.ACTIVE
                gc.completed_at = None
                svc._save_group(gc)

            # 注册 dag_id → group_id 映射
            svc._dag_groups[execution.dag_id] = execution.group_id

            # 注册项目经理
            from services.task_monitor_bot import (
                TaskMonitorBot, MONITOR_BOT_ID, MONITOR_BOT_NAME, MONITOR_BOT_EMOJI,
            )
            from models.group_chat import GroupParticipant, ParticipantRole
            if not gc.get_participant(MONITOR_BOT_ID):
                gc.add_participant(GroupParticipant(
                    participant_id=MONITOR_BOT_ID,
                    name=MONITOR_BOT_NAME,
                    role=ParticipantRole.MONITOR,
                    emoji=MONITOR_BOT_EMOJI,
                ))
                svc._save_group(gc)
            TaskMonitorBot.register(
                execution.dag_id, gc.group_id,
                execution.description, len(execution.nodes),
            )

            node_list = "\n".join(
                f"  {i+1}. {n.description}"
                + (f" (依赖: {', '.join(n.depends_on)})" if n.depends_on else "")
                for i, n in enumerate(execution.nodes.values())
            )
            await svc.post_message(
                gc.group_id, "main",
                f"🔄 续接任务，新增 {len(execution.nodes)} 个子任务:\n{node_list}",
                msg_type=GroupMessageType.PLAN,
                metadata={"total_nodes": len(execution.nodes), "resumed": True},
            )
            await svc.update_task_panel(
                gc.group_id,
                total=len(execution.nodes), completed=0, failed=0,
                running=0, pending=len(execution.nodes),
            )
            logger.info("群聊续接成功: %s → dag %s", execution.group_id, execution.dag_id)
        except Exception as e:
            logger.warning("续接群聊失败: %s", e)

    async def _group_post_task_assign(self, execution: DAGExecution, node: DAGNode) -> None:
        """主 Agent 在群聊中通知任务分配"""
        if not execution.group_id:
            return
        try:
            from services.group_chat_service import get_group_chat_service
            from models.group_chat import GroupMessageType
            svc = get_group_chat_service()
            duck_hint = f" → Duck({node.duck_id})" if node.duck_id else ""
            deps = f"（上游: {', '.join(node.depends_on)}）" if node.depends_on else ""
            await svc.post_message(
                execution.group_id, "main",
                f"📌 分配任务: {node.description}{duck_hint}{deps}",
                msg_type=GroupMessageType.TASK_ASSIGN,
                metadata={"node_id": node.node_id, "task_id": node.task_id},
            )
            # 项目经理: 记录任务分配
            from services.task_monitor_bot import TaskMonitorBot
            TaskMonitorBot.record_task_assign(
                execution.dag_id, node.node_id, node.description,
                duck_type=node.duck_type.value if node.duck_type else None,
            )
            # 更新面板
            all_n = list(execution.nodes.values())
            running = sum(1 for n in all_n if n.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING))
            pending = sum(1 for n in all_n if n.status == TaskStatus.PENDING)
            completed = sum(1 for n in all_n if n.status == TaskStatus.COMPLETED)
            failed = sum(1 for n in all_n if n.status == TaskStatus.FAILED)
            await svc.update_task_panel(
                execution.group_id,
                total=len(all_n), completed=completed, failed=failed,
                running=running, pending=pending,
            )
        except Exception as e:
            logger.debug("群聊任务分配消息失败: %s", e)

    async def _group_post_node_result(self, execution: DAGExecution, node: DAGNode, task: DuckTask) -> None:
        """Duck 在群聊中汇报任务结果，@主Agent"""
        if not execution.group_id:
            return
        try:
            from services.group_chat_service import get_group_chat_service
            from models.group_chat import GroupMessageType
            svc = get_group_chat_service()

            sender_id = task.assigned_duck_id or "system"
            # 确保 Duck 在参与者列表中
            gc = await svc.get_group(execution.group_id)
            if gc and sender_id != "system" and not gc.get_participant(sender_id):
                duck_name = f"Duck-{sender_id[:6]}"
                dtype = node.duck_type.value if node.duck_type else "general"
                await svc.add_duck_participant(execution.group_id, sender_id, duck_name, dtype)

            if task.status == TaskStatus.COMPLETED:
                output_preview = str(task.output)[:200] if task.output else "无输出"
                await svc.post_message(
                    execution.group_id, sender_id,
                    f"✅ @主Agent 任务完成: {node.description}\n结果: {output_preview}",
                    msg_type=GroupMessageType.TASK_COMPLETE,
                    mentions=["main"],
                    metadata={"node_id": node.node_id, "task_id": task.task_id},
                )
            else:
                await svc.post_message(
                    execution.group_id, sender_id,
                    f"❌ @主Agent 任务失败: {node.description}\n错误: {task.error or '未知错误'}",
                    msg_type=GroupMessageType.TASK_FAILED,
                    mentions=["main"],
                    metadata={"node_id": node.node_id, "task_id": task.task_id},
                )

            # 项目经理: 记录任务完成/失败
            from services.task_monitor_bot import TaskMonitorBot
            TaskMonitorBot.record_task_complete(
                execution.dag_id, node.node_id,
                output=task.output, error=task.error,
                success=(task.status == TaskStatus.COMPLETED),
            )

            # 更新面板
            all_n = list(execution.nodes.values())
            running = sum(1 for n in all_n if n.status in (TaskStatus.ASSIGNED, TaskStatus.RUNNING))
            pending = sum(1 for n in all_n if n.status == TaskStatus.PENDING)
            completed = sum(1 for n in all_n if n.status == TaskStatus.COMPLETED)
            failed = sum(1 for n in all_n if n.status == TaskStatus.FAILED)
            await svc.update_task_panel(
                execution.group_id,
                total=len(all_n), completed=completed, failed=failed,
                running=running, pending=pending,
            )
        except Exception as e:
            logger.debug("群聊节点结果消息失败: %s", e)

    async def _group_finalize(self, execution: DAGExecution) -> None:
        """DAG 完成/失败时更新群聊"""
        if not execution.group_id:
            return
        try:
            # ── 项目经理: 先发布分析报告 ──
            from services.task_monitor_bot import TaskMonitorBot
            await TaskMonitorBot.generate_and_post_report(execution.dag_id)
        except Exception as e:
            logger.debug("项目经理报告生成失败: %s", e)

        try:
            from services.group_chat_service import get_group_chat_service
            svc = get_group_chat_service()
            all_n = list(execution.nodes.values())
            completed_count = sum(1 for n in all_n if n.status == TaskStatus.COMPLETED)
            failed_count = sum(1 for n in all_n if n.status == TaskStatus.FAILED)

            if execution.status == "completed":
                conclusion = (
                    f"🎉 全部 {len(all_n)} 个子任务已完成"
                    f"（成功 {completed_count}，失败 {failed_count}）"
                )
                await svc.complete_group(execution.group_id, conclusion)
            else:
                await svc.fail_group(
                    execution.group_id,
                    f"共 {len(all_n)} 个子任务，成功 {completed_count}，失败 {failed_count}",
                )
        except Exception as e:
            logger.debug("群聊完结消息失败: %s", e)

    # ─── DAG 验证 ────────────────────────────────────

    @staticmethod
    def _has_cycle(nodes: List[DAGNode]) -> bool:
        """拓扑排序检测循环依赖"""
        graph: Dict[str, Set[str]] = {}
        in_degree: Dict[str, int] = {}

        for n in nodes:
            graph.setdefault(n.node_id, set())
            in_degree.setdefault(n.node_id, 0)

        for n in nodes:
            for dep in n.depends_on:
                graph.setdefault(dep, set()).add(n.node_id)
                in_degree[n.node_id] = in_degree.get(n.node_id, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            nid = queue.pop(0)
            visited += 1
            for succ in graph.get(nid, set()):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        return visited != len(nodes)


def get_dag_orchestrator() -> DAGTaskOrchestrator:
    return DAGTaskOrchestrator.get_instance()


def normalize_dag_dependencies(
    description: str,
    nodes_raw: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], bool]:
    """
    Normalize dependency declarations from user/LLM input.

    Safety rules:
    1. If no node provides any explicit depends_on
       AND the overall task clearly expresses sequential intent
       → auto-chain all nodes in listed order.

    2. If SOME nodes have explicit depends_on but others don't (partial edges)
       AND serial intent is detected
       → auto-chain nodes that lack depends_on to prevent them from running as parallel roots.
       This fixes the common case where the LLM provides depends_on for some nodes but
       forgets others, causing them to be dispatched simultaneously.
    """
    normalized = [dict(raw) for raw in nodes_raw]
    if len(normalized) < 2:
        return normalized, False

    nodes_with_edges = [raw for raw in normalized if bool((raw.get("depends_on") or []))]
    has_explicit_edges = len(nodes_with_edges) > 0
    all_have_edges = has_explicit_edges and len(nodes_with_edges) == len(normalized) - 1  # first node naturally has no deps

    # If ALL non-root nodes already have explicit depends_on, trust the LLM's structure
    if all_have_edges:
        return normalized, False

    joined_text = " ".join(
        [description or ""] + [str(raw.get("description") or "") for raw in normalized]
    )
    serial_intent = bool(
        re.search(
            r"(串行|按顺序|依次|顺序执行|分阶段|先.+再.+最后|先.+然后.+最后|步骤\d|阶段\d|上一阶段|下一阶段|基于前|等待.+完成后|sequential|in order|step by step)",
            joined_text,
            re.IGNORECASE,
        )
    )
    if not serial_intent:
        # 即使没有检测到串行意图，如果有部分 depends_on 且存在无依赖的非首节点，
        # 记录警告以帮助调试
        if has_explicit_edges:
            orphan_count = sum(
                1 for i, raw in enumerate(normalized)
                if i > 0 and not bool((raw.get("depends_on") or []))
            )
            if orphan_count > 0:
                logger.warning(
                    f"[normalize_dag] Partial depends_on detected: {len(nodes_with_edges)} nodes "
                    f"have edges, {orphan_count} non-root nodes have NO depends_on. "
                    f"These will run as parallel roots. If this is a serial task, "
                    f"add serial keywords to description."
                )
        return normalized, False

    # Auto-chain: 为缺少 depends_on 的非首节点补全串行依赖
    chained = False
    for idx in range(1, len(normalized)):
        if bool((normalized[idx].get("depends_on") or [])):
            continue  # 已有显式依赖，保留
        prev_node_id = str(normalized[idx - 1].get("node_id") or "").strip()
        if prev_node_id:
            normalized[idx]["depends_on"] = [prev_node_id]
            chained = True

    if chained:
        logger.info(
            f"[normalize_dag] Auto-chained serial dependencies for {len(normalized)} nodes "
            f"(had_partial_edges={has_explicit_edges})"
        )

    return normalized, chained


async def notify_duck_task_started(task_id: str, duck_id: str, duck_name: str) -> None:
    """Duck 开始执行任务时，在对应的 DAG 群聊中发送接受任务通知。

    由 local_duck_worker 在任务开始时调用，让群聊成员知道哪个 Duck 已接手并开始工作。
    """
    orchestrator = get_dag_orchestrator()
    entry = orchestrator._task_to_dag.get(task_id)
    if not entry:
        for _ in range(10):
            await asyncio.sleep(0.05)
            entry = orchestrator._task_to_dag.get(task_id)
            if entry:
                break
    if not entry:
        for dag_id, execution in orchestrator._executions.items():
            for node_id, node in execution.nodes.items():
                if node.task_id == task_id:
                    entry = (dag_id, node_id)
                    orchestrator._task_to_dag[task_id] = entry
                    break
            if entry:
                break
    if not entry:
        return                       # 该任务不属于任何 DAG（standalone duck task），静默跳过

    dag_id, node_id = entry
    execution = orchestrator._executions.get(dag_id)
    if not execution or not execution.group_id:
        return

    node = execution.nodes.get(node_id)
    if not node:
        return

    # 更新节点状态为 RUNNING
    node.status = TaskStatus.RUNNING
    node.duck_id = duck_id

    # 项目经理: 记录 Duck 开始执行
    try:
        from services.task_monitor_bot import TaskMonitorBot
        TaskMonitorBot.record_task_started(dag_id, node_id, duck_id)
    except Exception:
        pass

    try:
        from services.group_chat_service import get_group_chat_service
        from models.group_chat import GroupMessageType
        svc = get_group_chat_service()

        # 若 Duck 还不在群聊成员列表中，先加入
        gc = await svc.get_group(execution.group_id)
        if gc and not gc.get_participant(duck_id):
            dtype = node.duck_type.value if node.duck_type else "general"
            await svc.add_duck_participant(execution.group_id, duck_id, duck_name, dtype)

        await svc.post_message(
            execution.group_id, duck_id,
            f"⚙️ 已接收任务，开始执行：{node.description}",
            msg_type=GroupMessageType.TASK_PROGRESS,
            metadata={"node_id": node_id, "task_id": task_id},
        )
        # 更新任务面板
        all_n = list(execution.nodes.values())
        running = sum(1 for n in all_n if n.status in (TaskStatus.RUNNING, TaskStatus.ASSIGNED))
        pending = sum(1 for n in all_n if n.status == TaskStatus.PENDING)
        completed = sum(1 for n in all_n if n.status == TaskStatus.COMPLETED)
        failed = sum(1 for n in all_n if n.status == TaskStatus.FAILED)
        await svc.update_task_panel(
            execution.group_id,
            total=len(all_n), completed=completed, failed=failed,
            running=running, pending=pending,
        )
    except Exception as e:
        logger.debug("群聊 Duck 开始通知失败: %s", e)
