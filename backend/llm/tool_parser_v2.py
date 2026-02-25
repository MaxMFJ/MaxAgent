"""
Tool Call Parser v2 - 结构化解析，无复杂正则
使用 repair_json 提取工具调用
"""

from typing import Optional, Tuple

from .json_repair import repair_json


def parse_tool_call(text: str) -> Tuple[Optional[str], Optional[dict], str]:
    """
    从 LLM 输出解析工具调用
    
    Returns:
        (tool_name, args, remaining_text)
        - 若包含 tool 字段: (name, args_dict, remaining)
        - 否则: (None, None, text)
    """
    if not text or not isinstance(text, str):
        return None, None, text or ""

    text = text.strip()
    remaining = text

    # 1. 尝试 repair_json 解析
    data = repair_json(text)
    if data and isinstance(data, dict) and "tool" in data:
        name = data.get("tool")
        args = data.get("args")
        if name and isinstance(name, str):
            args = args if isinstance(args, dict) else {}
            name = name.strip()
            # 计算 remaining：去掉解析出的 JSON 部分
            # 优先尝试从多个候选块中匹配
            for block in _extract_brace_blocks(text):
                if repair_json(block) == data:
                    remaining = text.replace(block, "", 1).strip()
                    break
            else:
                remaining = ""
            return name, args, remaining

    return None, None, text


def _extract_brace_blocks(s: str) -> list:
    """提取 { } 块"""
    out = []
    depth = 0
    start = -1
    for i, c in enumerate(s):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(s[start : i + 1])
                start = -1
    return out
