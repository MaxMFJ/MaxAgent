"""
Delegate DAG Tool — 创建多Agent协作DAG（自动群聊）

供 Chat 模式（工具调用）使用。当用户的任务可分解为2+个有依赖关系的阶段时，
创建 DAG 编排多个 Duck 子Agent按依赖顺序（串行/并行）执行，并自动创建群聊。
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import BaseTool, ToolResult, ToolCategory

if TYPE_CHECKING:
    from runtime import RuntimeAdapter

logger = logging.getLogger(__name__)


class DelegateDagTool(BaseTool):
    """
    创建多Agent协作DAG，自动创建群聊供所有Agent实时汇报进度。
    当任务涉及2+个有依赖关系的阶段时使用（如 调研→分析→生成）。
    """

    name = "delegate_dag"
    description = (
        "创建多Agent协作DAG任务（自动群聊）。"
        "当任务可分解为2+个有依赖关系的阶段时使用（如 调研→分析→代码生成）。"
        "每个节点是一个子任务，depends_on定义执行顺序。无依赖的节点并行执行。"
        "参数：description(必填，总体描述)、nodes(必填，子任务节点数组)、existing_group_id(可选，续接已有群聊)。"
        "DAG会自动创建群聊，各Agent在群聊中汇报进度。如果用户要求续接已有群聊任务，传入existing_group_id。"
    )
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "任务的总体描述",
            },
            "nodes": {
                "type": "array",
                "description": "子任务节点列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "节点唯一ID（如 research, design, code）",
                        },
                        "description": {
                            "type": "string",
                            "description": "子任务描述",
                        },
                        "task_type": {
                            "type": "string",
                            "description": "Duck类型：crawler/coder/designer/tester/general",
                            "enum": ["crawler", "coder", "designer", "tester", "general"],
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "依赖的node_id列表，空=无依赖可并行",
                        },
                    },
                    "required": ["node_id", "description"],
                },
            },
            "existing_group_id": {
                "type": "string",
                "description": "（可选）续接已有协作群聊的 group_id。提供此参数时新DAG在该群聊中执行，不新建群聊。",
            },
        },
        "required": ["description", "nodes"],
    }

    def __init__(self, runtime_adapter: Optional["RuntimeAdapter"] = None):
        super().__init__(runtime_adapter)

    async def execute(self, **kwargs) -> ToolResult:
        description = (kwargs.get("description") or "").strip()
        nodes_raw = kwargs.get("nodes") or []
        existing_group_id = (kwargs.get("existing_group_id") or "").strip()

        if not description:
            return ToolResult(success=False, error="description 必填")
        if not nodes_raw or len(nodes_raw) < 2:
            return ToolResult(success=False, error="nodes 至少需要2个子任务节点")

        try:
            from app_state import IS_DUCK_MODE
            if IS_DUCK_MODE:
                return ToolResult(success=False, error="Duck 模式下不允许创建 DAG 协作任务")

            from services.duck_task_dag import (
                DAGTaskOrchestrator,
                DAGNode,
                normalize_dag_dependencies,
            )
            from services.duck_protocol import DuckType

            nodes_raw, auto_chained = normalize_dag_dependencies(description, nodes_raw)

            # 解析节点
            dag_nodes = []
            for raw in nodes_raw:
                node_id = (raw.get("node_id") or "").strip()
                node_desc = (raw.get("description") or "").strip()
                if not node_id or not node_desc:
                    return ToolResult(success=False, error=f"每个 node 必须包含 node_id 和 description")

                duck_type = None
                task_type = raw.get("task_type", "general")
                if task_type:
                    try:
                        duck_type = DuckType(task_type)
                    except ValueError:
                        pass

                # 展开路径
                desktop_path = os.path.realpath(os.path.expanduser("~/Desktop"))
                enhanced_desc = (
                    f"{node_desc}\n"
                    f"【重要】保存文件时必须使用实际路径：{desktop_path}，禁止用 /Users/xxx/ 或 $(whoami)。"
                )

                dag_nodes.append(DAGNode(
                    node_id=node_id,
                    description=enhanced_desc,
                    task_type=task_type,
                    duck_type=duck_type,
                    timeout=600,
                    depends_on=raw.get("depends_on") or [],
                    input_mapping=raw.get("input_mapping") or {},
                ))

            orchestrator = DAGTaskOrchestrator.get_instance()
            from services.duck_task_scheduler import get_task_scheduler

            # 获取当前 session_id
            from agent.terminal_session import get_current_session_id
            session_id = (
                get_current_session_id()
                or getattr(self, "_current_session_id", "")
                or ""
            )
            if not session_id:
                return ToolResult(
                    success=False,
                    error="delegate_dag 需要有效的当前会话，当前未获取到 session_id",
                )

            scheduler = get_task_scheduler()
            await scheduler.initialize()

            execution = orchestrator.create_dag(
                description=description,
                nodes=dag_nodes,
                session_id=session_id,
                existing_group_id=existing_group_id or None,
            )

            # 异步执行（不阻塞）
            asyncio.create_task(orchestrator.execute(execution.dag_id))

            node_summary = ", ".join(
                f"{n.node_id}({'→'.join(n.depends_on) if n.depends_on else '并行'})"
                for n in dag_nodes
            )

            group_msg = f"群聊 {existing_group_id} 中续接执行" if existing_group_id else "群聊已自动创建，各Agent将在群聊中实时汇报进度"
            chain_msg = ""
            if auto_chained:
                chain_msg = "\n检测到这是顺序任务，已自动按节点顺序补全 depends_on 串行依赖。"

            return ToolResult(
                success=True,
                data={
                    "dag_id": execution.dag_id,
                    "node_count": len(dag_nodes),
                    "group_id": execution.group_id,
                    "message": (
                        f"多Agent协作DAG已创建并开始执行（共{len(dag_nodes)}个子任务）。\n"
                        f"节点：{node_summary}\n"
                        f"{group_msg}。{chain_msg}"
                    ),
                },
            )

        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except ImportError as e:
            logger.warning("DAG orchestrator not available: %s", e)
            return ToolResult(success=False, error="DAG 编排器不可用")
        except Exception as e:
            logger.exception("delegate_dag tool error")
            return ToolResult(success=False, error=f"创建DAG失败: {e}")
