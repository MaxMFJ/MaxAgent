"""
ACP Phase 2 — Capability Graph Route

GET /agent/capabilities
提供机器可读的能力图谱，聚合 tools、capsules、ducks 数据。
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from models.acp_models import (
    CapabilityGraph,
    CapabilityNodes,
    CapsuleNode,
    DuckTypeNode,
    ToolNode,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ACP"])


def _build_tool_nodes() -> List[ToolNode]:
    """从 ToolRegistry 聚合工具节点。"""
    nodes: List[ToolNode] = []
    try:
        from app_state import get_agent_core
        core = get_agent_core()
        if not core:
            return nodes
        for tool in core.registry.list_tools():
            schema = tool.to_function_schema()
            params = schema.get("parameters", {})
            nodes.append(ToolNode(
                id=f"tool:{tool.name}",
                name=tool.name,
                description=tool.description or "",
                tags=[tool.category.value] if hasattr(tool, "category") and tool.category else [],
                input_schema=params,
                autonomous_safe=True,
            ))
    except Exception as e:
        logger.warning("Failed to build tool nodes: %s", e)
    return nodes


def _build_capsule_nodes() -> List[CapsuleNode]:
    """从 CapsuleRegistry 聚合 capsule 节点。"""
    nodes: List[CapsuleNode] = []
    try:
        from agent.capsule_registry import get_capsule_registry
        registry = get_capsule_registry()
        for cap in registry.list_capsules():
            nodes.append(CapsuleNode(
                id=f"capsule:{cap.id}",
                name=cap.name,
                task_type=getattr(cap, "task_type", ""),
                tags=getattr(cap, "tags", []),
                capability=getattr(cap, "capability", []),
            ))
    except Exception as e:
        logger.warning("Failed to build capsule nodes: %s", e)
    return nodes


async def _build_duck_nodes() -> List[DuckTypeNode]:
    """从 DuckRegistry 聚合 duck 类型节点。"""
    nodes: List[DuckTypeNode] = []
    try:
        from services.duck_registry import DuckRegistry
        from services.duck_protocol import DuckType

        registry = DuckRegistry.get_instance()
        all_ducks = await registry.list_all()

        # 按类型聚合
        type_counts: Dict[str, Dict[str, int]] = {}
        for dt in DuckType:
            type_counts[dt.value] = {"available": 0, "busy": 0}

        for duck in all_ducks:
            dt = duck.duck_type.value if hasattr(duck.duck_type, "value") else str(duck.duck_type)
            if dt not in type_counts:
                type_counts[dt] = {"available": 0, "busy": 0}
            status = duck.status.value if hasattr(duck.status, "value") else str(duck.status)
            if status == "online":
                type_counts[dt]["available"] += 1
            elif status == "busy":
                type_counts[dt]["busy"] += 1

        for dt_name, counts in type_counts.items():
            nodes.append(DuckTypeNode(
                id=f"duck:{dt_name.lower()}",
                variant=dt_name.upper(),
                specialty=[dt_name.lower()],
                available_count=counts["available"],
                busy_count=counts["busy"],
            ))
    except Exception as e:
        logger.warning("Failed to build duck nodes: %s", e)
    return nodes


def _build_relations(
    tools: List[ToolNode],
    ducks: List[DuckTypeNode],
) -> List[Dict[str, str]]:
    """构建能力关系。"""
    relations = []
    # 所有 duck 可以使用所有工具
    for duck in ducks:
        for tool in tools:
            relations.append({
                "from": duck.id,
                "target": tool.id,
                "type": "can_use",
            })
    return relations


@router.get("/capabilities")
async def capability_graph(
    format: str = Query("graph", description="graph|flat|openapi"),
):
    """
    能力图谱 — 机器可读的 tools、capsules、ducks 关系。
    """
    tools = _build_tool_nodes()
    capsules = _build_capsule_nodes()
    ducks = await _build_duck_nodes()

    if format == "flat":
        return {
            "tools": [t.model_dump() for t in tools],
            "capsules": [c.model_dump() for c in capsules],
            "duck_types": [d.model_dump() for d in ducks],
        }

    relations = _build_relations(tools, ducks)
    graph = CapabilityGraph(
        nodes=CapabilityNodes(
            tools=tools,
            capsules=capsules,
            duck_types=ducks,
        ),
        relations=relations,
    )
    return graph.model_dump(by_alias=True)
