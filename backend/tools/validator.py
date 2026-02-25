"""
Tool Validator - 工具调用校验
校验工具存在性、参数合法性、enum、必填字段
"""

from typing import Tuple

from .schema_registry import get_tool, validate_args


def validate_tool_call(name: str, args: dict) -> Tuple[bool, str | None]:
    """
    校验工具调用是否合法
    
    Returns:
        (valid, error_message)
        - valid=True 时 error 为 None
        - valid=False 时 error 为错误描述
    """
    if not name or not isinstance(name, str):
        return False, "工具名为空"
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return False, "args 必须为对象"

    valid, err = validate_args(name, args)
    return valid, err
