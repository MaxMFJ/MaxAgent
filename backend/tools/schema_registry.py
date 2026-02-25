"""
Tool Schema Registry - 工具结构化注册表
为 Tool Runtime v2 提供 name/description/args schema，可动态扩展
与 ToolRegistry 解耦：Schema 仅负责定义，执行由 router 完成
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 结构化工具 schema：{name: {description, args}}
# args: {param_name: {type, enum?, description?}}
TOOLS: Dict[str, Dict[str, Any]] = {}


def build_from_base_tools(tools: list) -> None:
    """
    从 BaseTool 实例列表构建 schema
    可动态扩展，支持 tools 运行时加载
    """
    global TOOLS
    for tool in tools:
        if not hasattr(tool, "name") or not tool.name:
            continue
        params = getattr(tool, "parameters", {})
        props = params.get("properties", {})
        required = params.get("required", [])
        args_schema = {}
        for key, spec in props.items():
            arg = {"type": spec.get("type", "string")}
            if "enum" in spec:
                arg["enum"] = spec["enum"]
            if "description" in spec:
                arg["description"] = spec["description"]
            if key in required:
                arg["required"] = True
            args_schema[key] = arg
        TOOLS[tool.name] = {
            "description": getattr(tool, "description", "") or "",
            "args": args_schema,
            "required": required,
        }
    logger.info(f"Schema registry built: {len(TOOLS)} tools")


def register_tool(name: str, description: str, args: Dict[str, Any], required: Optional[list] = None) -> None:
    """动态注册单个工具 schema"""
    TOOLS[name] = {
        "description": description,
        "args": args,
        "required": required or [],
    }
    logger.info(f"Registered schema: {name}")


def get_tool(name: str) -> Optional[Dict[str, Any]]:
    """获取工具 schema"""
    return TOOLS.get(name)


def validate_args(tool_name: str, args: dict) -> Tuple[bool, Optional[str]]:
    """
    校验参数是否符合工具 schema
    Returns:
        (valid, error_message)
    """
    tool = get_tool(tool_name)
    if not tool:
        return False, f"未知工具: {tool_name}"
    if not isinstance(args, dict):
        return False, "args 必须是对象"

    schema_args = tool.get("args", {})
    required = tool.get("required", [])

    for param in required:
        if param not in args or args[param] is None:
            return False, f"缺少必需参数: {param}"

    for key, value in args.items():
        if key not in schema_args:
            # 允许多余参数，忽略
            continue
        spec = schema_args[key]
        if value is None and key not in required:
            continue
        if "enum" in spec:
            if value not in spec["enum"]:
                return False, f"参数 {key} 必须是 {spec['enum']} 之一"
        if "type" in spec:
            t = spec["type"]
            if t == "string" and not isinstance(value, str):
                try:
                    str(value)
                except Exception:
                    return False, f"参数 {key} 应为字符串"
            elif t == "integer" and not isinstance(value, (int, float)):
                try:
                    int(value)
                except (ValueError, TypeError):
                    return False, f"参数 {key} 应为整数"
            elif t == "number" and not isinstance(value, (int, float)):
                try:
                    float(value)
                except (ValueError, TypeError):
                    return False, f"参数 {key} 应为数字"
            elif t == "boolean" and not isinstance(value, bool):
                if isinstance(value, str) and value.lower() in ("true", "1", "yes"):
                    pass
                elif not isinstance(value, bool):
                    return False, f"参数 {key} 应为布尔值"

    return True, None


def list_tool_names() -> list:
    """列出所有已注册工具名"""
    return list(TOOLS.keys())
