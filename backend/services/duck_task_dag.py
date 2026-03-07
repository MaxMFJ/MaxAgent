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
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    status: str = "pending"   # pending / running / completed / failed / cancelled
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    output: Any = None        # 聚合后的最终结果
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "dag_id": self.dag_id,
            "description": self.description,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "output": self.output,
            "error": self.error,
        }


class DAGTaskOrchestrator:
    """DAG 任务编排器（单例）"""

    _instance: Optional["DAGTaskOrchestrator"] = None

    def __init__(self):
        self._executions: Dict[str, DAGExecution] = {}
        self._task_to_dag: Dict[str, tuple[str, str]] = {}  # task_id → (dag_id, node_id)
        self._callbacks: Dict[str, DAGCallback] = {}

    @classmethod
    def get_instance(cls) -> "DAGTaskOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 创建 DAG ────────────────────────────────────

    def create_dag(
        self,
        description: str,
        nodes: List[DAGNode],
        callback: Optional[DAGCallback] = None,
    ) -> DAGExecution:
        """
        创建一个 DAG 执行实例。
        nodes 列表中的 depends_on 字段定义依赖关系。
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
            nodes={n.node_id: n for n in nodes},
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

        # 触发回调
        cb = self._callbacks.pop(execution.dag_id, None)
        if cb:
            try:
                await cb(execution)
            except Exception as e:
                logger.error(f"DAG callback error: {e}")

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
