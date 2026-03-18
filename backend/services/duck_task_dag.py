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


class DAGTaskOrchestrator:
    """DAG 任务编排器（单例）"""

    _instance: Optional["DAGTaskOrchestrator"] = None
    _complete_hooks: List[Callable] = []  # 全局完成钩子

    def __init__(self):
        self._executions: Dict[str, DAGExecution] = {}
        self._task_to_dag: Dict[str, tuple[str, str]] = {}  # task_id → (dag_id, node_id)
        self._callbacks: Dict[str, DAGCallback] = {}

    @classmethod
    def get_instance(cls) -> "DAGTaskOrchestrator":
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

        self._executions[dag_id] = execution
        if callback:
            self._callbacks[dag_id] = callback

        logger.info(f"DAG created: {dag_id} with {len(nodes)} nodes")
        return execution

    # ─── 执行 DAG ────────────────────────────────────

    async def execute(self, dag_id: str):
        """执行 DAG：按依赖顺序分发任务"""
        execution = self._executions.get(dag_id)
        if not execution:
            raise ValueError(f"DAG not found: {dag_id}")

        execution.status = "running"
        logger.info(f"DAG executing: {dag_id}")

        # 群聊：复用已有群聊或新建
        if execution.session_id:
            if execution.group_id:
                await self._reuse_group_chat(execution)
            else:
                await self._create_group_chat(execution)

        # 启动所有无依赖的节点
        await self._schedule_ready_nodes(execution)

    async def _schedule_ready_nodes(self, execution: DAGExecution):
        """找出所有可以开始的节点并提交"""
        from services.duck_task_scheduler import get_task_scheduler

        scheduler = get_task_scheduler()

        for node in execution.nodes.values():
            if node.status != TaskStatus.PENDING:
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
            self._task_to_dag[task.task_id] = (execution.dag_id, node.node_id)

            logger.info(f"DAG {execution.dag_id}: node {node.node_id} → task {task.task_id}")

            # 群聊: 主 Agent 发布任务分配消息
            await self._group_post_task_assign(execution, node)

    async def _on_node_complete(self, dag_id: str, node_id: str, task: DuckTask):
        """节点任务完成回调"""
        execution = self._executions.get(dag_id)
        if not execution:
            return

        node = execution.nodes.get(node_id)
        if not node:
            return

        node.status = task.status
        node.output = task.output
        node.error = task.error

        logger.info(f"DAG {dag_id}: node {node_id} → {task.status.value}")

        # 群聊: Duck 汇报完成/失败
        await self._group_post_node_result(execution, node, task)

        if task.status == TaskStatus.FAILED:
            # 检查是否还有其他节点可以执行
            # 如果失败节点是后续节点的依赖，则这些后续节点也标记为失败
            self._propagate_failure(execution, node_id)

        # 检查是否可以启动更多节点
        await self._schedule_ready_nodes(execution)

        # 检查 DAG 是否全部完成
        await self._check_dag_completion(execution)

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
        pending = [n for n in all_nodes if n.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING)]

        if pending:
            return  # 还有节点在执行或等待

        # 所有节点完成
        completed = [n for n in all_nodes if n.status == TaskStatus.COMPLETED]
        failed = [n for n in all_nodes if n.status == TaskStatus.FAILED]

        execution.completed_at = time.time()

        if completed:
            execution.status = "completed"
            # 聚合结果：找到终端节点（无后继节点的节点）
            terminal_nodes = self._find_terminal_nodes(execution)
            execution.output = {
                "total_nodes": len(all_nodes),
                "completed": len(completed),
                "failed": len(failed),
                "results": {
                    n.node_id: {"output": n.output, "description": n.description}
                    for n in terminal_nodes if n.status == TaskStatus.COMPLETED
                },
            }
        else:
            execution.status = "failed"
            execution.error = f"All {len(failed)} nodes failed"
            execution.output = {
                "errors": {
                    n.node_id: {"error": n.error, "description": n.description}
                    for n in failed
                }
            }

        logger.info(f"DAG {execution.dag_id} finished: {execution.status}")

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
        """DAG 开始时自动创建群聊"""
        try:
            from services.group_chat_service import get_group_chat_service
            svc = get_group_chat_service()
            gc = await svc.create_group(
                session_id=execution.session_id,
                title=execution.description,
                dag_id=execution.dag_id,
            )
            execution.group_id = gc.group_id

            # ── 项目经理机器人自动加入 ──
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

            # 主 Agent 在群聊中发布执行计划
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
            logger.warning("创建群聊失败: %s", e)

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


async def notify_duck_task_started(task_id: str, duck_id: str, duck_name: str) -> None:
    """Duck 开始执行任务时，在对应的 DAG 群聊中发送接受任务通知。

    由 local_duck_worker 在任务开始时调用，让群聊成员知道哪个 Duck 已接手并开始工作。
    """
    orchestrator = get_dag_orchestrator()
    entry = orchestrator._task_to_dag.get(task_id)
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
