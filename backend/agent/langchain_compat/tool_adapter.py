"""
将 MacAgent ToolRegistry / BaseTool 适配为 LangChain BaseTool
使现有工具可在 create_tool_calling_agent、LCEL 中使用
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tools.registry import ToolRegistry
    from tools.base import BaseTool

try:
    from langchain_core.tools import StructuredTool, BaseTool as LCBaseTool
    from langchain_core.callbacks import AsyncCallbackManagerForToolRun
    from pydantic import BaseModel, Field, create_model

    _HAS_LC = True
except ImportError:
    _HAS_LC = False
    StructuredTool = None  # type: ignore
    LCBaseTool = None  # type: ignore


def _tool_result_to_str(success: bool, data: Any = None, error: Optional[str] = None) -> str:
    """与 MacAgent ToolResult.to_string() 行为一致，供 LLM 消费"""
    if not success:
        return f"错误: {error}"
    if isinstance(data, dict):
        import json
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif isinstance(data, list):
        import json
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = str(data) if data else "操作成功"
    max_chars = 3000
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...[结果已截断，原始长度 {len(text)} 字符]"
    return text


def _make_langchain_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    execute_fn: Any,
    registry: Any,
    bind_target_fn: Optional[Any] = None,
) -> "LCBaseTool":
    """
    为单个 MacAgent 工具创建一个 LangChain StructuredTool，执行时委托 router.execute_tool。
    """
    if not _HAS_LC:
        raise RuntimeError("langchain-core is required. Install with: pip install -r requirements-langchain.txt")

    # 从 parameters 构建 Pydantic 模型（简化：properties 的 key 映射为类型）
    props = parameters.get("properties") or {}
    required = set(parameters.get("required") or [])
    fields = {}
    for k, v in props.items():
        t = str
        if isinstance(v, dict) and "type" in v:
            typ = v["type"]
            if typ == "integer":
                t = int
            elif typ == "number":
                t = float
            elif typ == "boolean":
                t = bool
            elif typ == "array":
                t = list
            elif typ == "object":
                t = dict
        default = None if k not in required else ...
        fields[k] = (t, default)
    args_schema = create_model(f"Args_{name}", **fields) if fields else None

    async def _arun(**kwargs: Any) -> str:
        from tools.router import execute_tool
        result = await execute_tool(
            name,
            kwargs or {},
            registry=registry,
            bind_target_fn=bind_target_fn,
        )
        return _tool_result_to_str(result.success, result.data, result.error)

    return StructuredTool.from_function(
        name=name,
        description=description,
        func=_arun,
        args_schema=args_schema,
    )


def mac_tools_to_langchain(
    registry: "ToolRegistry",
    query: str = "",
    max_tools: int = 8,
    always_include: Optional[List[str]] = None,
    bind_target_fn: Optional[Any] = None,
) -> List["LCBaseTool"]:
    """
    将 MacAgent 工具集转为 LangChain 工具列表。
    若提供 query，则使用 registry.get_relevant_schemas 做语义裁剪；否则使用全部 schema。
    """
    if not _HAS_LC:
        raise RuntimeError("langchain-core is required. Install with: pip install -r requirements-langchain.txt")

    if query:
        schemas = registry.get_relevant_schemas(
            query,
            max_tools=max_tools,
            always_include=always_include or ["terminal", "file_operations", "app_control"],
        )
    else:
        schemas = registry.get_schemas()

    tools = []
    for s in schemas:
        name = s.get("name", "")
        desc = s.get("description", "")
        params = s.get("parameters", {"type": "object", "properties": {}, "required": []})
        t = registry.get(name)
        if not t:
            continue
        lc_tool = _make_langchain_tool(
            name=name,
            description=desc,
            parameters=params,
            execute_fn=t.execute,
            registry=registry,
            bind_target_fn=bind_target_fn,
        )
        tools.append(lc_tool)
    return tools
