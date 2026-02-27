"""
v3.1 统一安全校验：危险命令/路径/工具参数
在 _execute_action 入口调用，覆盖 run_shell、call_tool、写文件等。
"""
import os
import logging
from typing import Tuple

from .action_schema import AgentAction, ActionType

logger = logging.getLogger(__name__)

# 危险命令模式（与原 _is_dangerous_command 对齐并扩展）
DANGEROUS_COMMAND_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "chmod -R 777 /",
    "> /dev/sda",
    "mv /* ",
    "sudo rm ",
    "format ",
    "> /dev/",
]

# 禁止写入/删除的系统路径前缀
DANGEROUS_PATH_PREFIXES = [
    "/System", "/Library", "/usr", "/bin", "/sbin", "/private/var",
    os.path.expanduser("~/.ssh"),
]
# 禁止删除的根级
DANGEROUS_PATH_EXACT = ["/", "/usr", "/bin", "/sbin", "/System", "/Library"]


def _normalize_path(p: str) -> str:
    if not p:
        return ""
    return os.path.normpath(p).rstrip("/")


def validate_command(command: str) -> Tuple[bool, str]:
    """校验命令是否包含危险模式。返回 (ok, error_message)。"""
    if not command or not isinstance(command, str):
        return True, ""
    cmd_lower = command.strip().lower()
    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"危险命令被拦截: 包含模式 '{pattern}'"
    return True, ""


def validate_path_for_write(path: str) -> Tuple[bool, str]:
    """校验写文件路径是否在允许范围内。"""
    p = _normalize_path(path)
    if not p:
        return True, ""
    for prefix in DANGEROUS_PATH_PREFIXES:
        if p == prefix or p.startswith(prefix + "/"):
            return False, f"禁止写入系统路径: {path}"
    for exact in DANGEROUS_PATH_EXACT:
        if p == exact or p.startswith(exact + "/"):
            return False, f"禁止写入系统路径: {path}"
    return True, ""


def validate_path_for_delete(path: str) -> Tuple[bool, str]:
    """校验删除路径。"""
    p = _normalize_path(path)
    if not p:
        return True, ""
    for exact in DANGEROUS_PATH_EXACT:
        if p == exact or p.startswith(exact + "/"):
            return False, f"禁止删除系统路径: {path}"
    for prefix in DANGEROUS_PATH_PREFIXES:
        if p == prefix or p.startswith(prefix + "/"):
            return False, f"禁止删除系统路径: {path}"
    return True, ""


def validate_action_safe(action: AgentAction) -> Tuple[bool, str]:
    """
    统一校验动作是否允许执行（危险命令/路径/工具参数）。
    返回 (ok, error_message)。在 _execute_action 入口调用。
    """
    params = action.params or {}
    atype = action.action_type

    if atype == ActionType.RUN_SHELL:
        cmd = params.get("command", "")
        return validate_command(cmd)

    if atype == ActionType.CREATE_AND_RUN_SCRIPT:
        code = params.get("code", "")
        if code and isinstance(code, str):
            code_lower = code.lower()
            for pattern in DANGEROUS_COMMAND_PATTERNS:
                if pattern.lower() in code_lower:
                    return False, f"脚本内容包含危险模式被拦截: '{pattern}'"
        return True, ""

    if atype == ActionType.WRITE_FILE:
        path = params.get("path", "")
        return validate_path_for_write(path)

    if atype == ActionType.DELETE_FILE:
        path = params.get("path", "")
        return validate_path_for_delete(path)

    if atype == ActionType.MOVE_FILE:
        dest = params.get("destination", "")
        ok, err = validate_path_for_write(dest)
        if not ok:
            return ok, err
        return True, ""

    if atype == ActionType.CALL_TOOL:
        tool_name = (params.get("tool_name") or "").strip().lower()
        args = params.get("args") or {}
        if not isinstance(args, dict):
            return True, ""
        # terminal / script 类工具：校验 command 或 code
        if tool_name in ("terminal", "run_shell", "shell"):
            cmd = args.get("command") or args.get("cmd") or ""
            return validate_command(str(cmd))
        if tool_name in ("script", "run_script"):
            code = args.get("code") or args.get("script") or ""
            if code:
                code_lower = str(code).lower()
                for pattern in DANGEROUS_COMMAND_PATTERNS:
                    if pattern.lower() in code_lower:
                        return False, f"工具 {tool_name} 参数包含危险模式被拦截"
        return True, ""

    return True, ""
