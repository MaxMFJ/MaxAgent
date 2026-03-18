"""
Task Monitor Bot — 群聊项目经理机器人

每个 DAG 群聊自动加入，负责:
- 记录任务执行步骤与时间戳
- 分析执行过程与瓶颈
- 收集各节点结果
- 在 DAG 完成/失败后发送总结报告（含问题、优化建议等）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 机器人身份 ────────────────────────────────────────────────────

MONITOR_BOT_ID = "monitor_bot"
MONITOR_BOT_NAME = "项目经理"
MONITOR_BOT_EMOJI = "📊"


# ── 节点时间线 ────────────────────────────────────────────────────


@dataclass
class NodeTimeline:
    """单个节点的执行时间线"""
    node_id: str
    description: str
    duck_type: Optional[str] = None
    assigned_duck_id: Optional[str] = None

    # 时间戳
    assigned_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    # 结果
    status: str = "pending"
    output_preview: Optional[str] = None
    error: Optional[str] = None

    @property
    def wait_duration(self) -> Optional[float]:
        """等待时间: 分配 → 开始执行"""
        if self.assigned_at and self.started_at:
            return self.started_at - self.assigned_at
        return None

    @property
    def exec_duration(self) -> Optional[float]:
        """执行时间: 开始 → 完成"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def total_duration(self) -> Optional[float]:
        """总耗时: 分配 → 完成"""
        if self.assigned_at and self.completed_at:
            return self.completed_at - self.assigned_at
        return None


@dataclass
class DAGMonitorData:
    """单个 DAG 的完整监控数据"""
    dag_id: str
    group_id: str
    description: str
    total_nodes: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    nodes: Dict[str, NodeTimeline] = field(default_factory=dict)


# ── 项目经理机器人 ────────────────────────────────────────────────


class TaskMonitorBot:
    """
    群聊项目经理机器人（全局单例）

    在每个 DAG 群聊中自动加入，记录全部执行事件，
    DAG 完成/失败后生成分析报告发送到群聊。
    """

    _monitors: Dict[str, DAGMonitorData] = {}  # dag_id → monitor data

    # ── 注册 / 清理 ──────────────────────────────────

    @classmethod
    def register(cls, dag_id: str, group_id: str, description: str, total_nodes: int) -> None:
        """DAG 创建时注册监控"""
        cls._monitors[dag_id] = DAGMonitorData(
            dag_id=dag_id,
            group_id=group_id,
            description=description,
            total_nodes=total_nodes,
        )
        logger.info("📊 项目经理已加入: dag=%s group=%s", dag_id, group_id)

    @classmethod
    def cleanup(cls, dag_id: str) -> None:
        cls._monitors.pop(dag_id, None)

    # ── 事件记录 ─────────────────────────────────────

    @classmethod
    def record_task_assign(
        cls, dag_id: str, node_id: str, description: str,
        duck_type: Optional[str] = None,
    ) -> None:
        """记录: 主 Agent 分配任务"""
        monitor = cls._monitors.get(dag_id)
        if not monitor:
            return
        monitor.nodes[node_id] = NodeTimeline(
            node_id=node_id,
            description=description,
            duck_type=duck_type,
            assigned_at=time.time(),
            status="assigned",
        )

    @classmethod
    def record_task_started(cls, dag_id: str, node_id: str, duck_id: str) -> None:
        """记录: Duck 开始执行"""
        monitor = cls._monitors.get(dag_id)
        if not monitor:
            return
        node = monitor.nodes.get(node_id)
        if node:
            node.started_at = time.time()
            node.assigned_duck_id = duck_id
            node.status = "running"

    @classmethod
    def record_task_complete(
        cls, dag_id: str, node_id: str,
        output: Any = None, error: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """记录: 任务完成或失败"""
        monitor = cls._monitors.get(dag_id)
        if not monitor:
            return
        node = monitor.nodes.get(node_id)
        if node:
            node.completed_at = time.time()
            node.status = "completed" if success else "failed"
            node.error = error
            if output:
                node.output_preview = str(output)[:150]

    # ── 报告生成与发送 ───────────────────────────────

    @classmethod
    async def generate_and_post_report(cls, dag_id: str) -> None:
        """生成分析报告并发送到群聊"""
        monitor = cls._monitors.get(dag_id)
        if not monitor:
            return

        monitor.completed_at = time.time()
        report = cls._build_report(monitor)

        try:
            from services.group_chat_service import get_group_chat_service
            from models.group_chat import GroupMessageType

            svc = get_group_chat_service()
            await svc.post_message(
                monitor.group_id,
                MONITOR_BOT_ID,
                report,
                msg_type=GroupMessageType.MONITOR_REPORT,
                metadata={"dag_id": dag_id, "type": "final_report"},
            )
        except Exception as e:
            logger.error("项目经理报告发送失败: %s", e)

        # 发送完毕后清理
        cls._monitors.pop(dag_id, None)

    # ── 报告内容 ─────────────────────────────────────

    @classmethod
    def _build_report(cls, data: DAGMonitorData) -> str:
        nodes = list(data.nodes.values())
        completed = [n for n in nodes if n.status == "completed"]
        failed = [n for n in nodes if n.status == "failed"]
        total_time = (data.completed_at or time.time()) - data.created_at

        lines: List[str] = []

        # ── 概览 ──
        lines.append("📊 **项目经理 · 任务执行报告**")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"📋 任务: {data.description}")
        lines.append(f"⏱ 总耗时: {cls._fmt(total_time)}")
        result_str = f"{len(completed)}/{data.total_nodes} 成功"
        if failed:
            result_str += f"，{len(failed)} 失败"
        lines.append(f"📈 结果: {result_str}")
        lines.append("")

        # ── 各节点详情 ──
        lines.append("**📝 执行详情:**")
        for i, node in enumerate(nodes, 1):
            icon = {"completed": "✅", "failed": "❌"}.get(node.status, "⏳")
            exec_t = cls._fmt(node.exec_duration) if node.exec_duration else "N/A"
            wait_t = cls._fmt(node.wait_duration) if node.wait_duration else "N/A"
            lines.append(f"  {icon} {i}. {node.description}")
            lines.append(f"     执行: {exec_t} | 等待: {wait_t}")
            if node.error:
                lines.append(f"     ⚠️ 错误: {node.error[:100]}")
        lines.append("")

        # ── 问题分析 ──
        problems = cls._analyze_problems(nodes)
        if problems:
            lines.append("**⚠️ 问题分析:**")
            for p in problems:
                lines.append(f"  • {p}")
            lines.append("")

        # ── 优化建议 ──
        suggestions = cls._generate_suggestions(data, nodes)
        if suggestions:
            lines.append("**💡 优化建议:**")
            for s in suggestions:
                lines.append(f"  • {s}")

        return "\n".join(lines)

    @classmethod
    def _analyze_problems(cls, nodes: List[NodeTimeline]) -> List[str]:
        problems: List[str] = []

        # 失败任务
        for n in nodes:
            if n.status == "failed":
                problems.append(f"任务「{n.description}」执行失败: {n.error or '未知原因'}")

        # 等待过长 (>30s)
        long_wait = sorted(
            [n for n in nodes if n.wait_duration and n.wait_duration > 30],
            key=lambda n: n.wait_duration or 0, reverse=True,
        )
        for n in long_wait:
            problems.append(
                f"任务「{n.description}」等待调度耗时 {cls._fmt(n.wait_duration)}，"
                f"可能 Duck 资源不足"
            )

        # 执行过长 (>2min)
        long_exec = sorted(
            [n for n in nodes if n.exec_duration and n.exec_duration > 120],
            key=lambda n: n.exec_duration or 0, reverse=True,
        )
        for n in long_exec:
            problems.append(
                f"任务「{n.description}」执行耗时 {cls._fmt(n.exec_duration)}，"
                f"建议关注是否可拆分"
            )

        return problems

    @classmethod
    def _generate_suggestions(cls, data: DAGMonitorData, nodes: List[NodeTimeline]) -> List[str]:
        suggestions: List[str] = []
        failed = [n for n in nodes if n.status == "failed"]
        completed = [n for n in nodes if n.status == "completed"]

        # 高失败率
        if failed and len(failed) >= len(nodes) * 0.5:
            suggestions.append("失败率较高，建议检查任务描述是否清晰，或拆解为更小粒度的子任务")

        # 长等待
        if any(n.wait_duration and n.wait_duration > 30 for n in nodes):
            suggestions.append("部分任务等待调度时间较长，建议增加 Duck 并发数或优化任务分配策略")

        # 长执行
        if any(n.exec_duration and n.exec_duration > 120 for n in nodes):
            suggestions.append("部分任务执行时间较长，建议拆分为更小的原子操作以提升并行度")

        # 低并行度
        if len(nodes) > 2:
            serial = sum(1 for n in nodes if n.wait_duration and n.wait_duration > 5)
            if serial > len(nodes) * 0.7:
                suggestions.append("大部分任务串行执行，建议优化 DAG 依赖关系以提升并行度")

        # 全部成功
        if not failed and completed:
            total = (data.completed_at or time.time()) - data.created_at
            if total < 60:
                suggestions.append("任务执行高效，无需优化 👍")
            else:
                suggestions.append("任务全部成功完成，可关注总耗时优化")

        return suggestions

    @staticmethod
    def _fmt(seconds: Optional[float]) -> str:
        if seconds is None:
            return "N/A"
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}m{s:.0f}s"
