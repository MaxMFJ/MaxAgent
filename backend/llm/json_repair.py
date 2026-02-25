"""
JSON Repair - 本地模型输出修复器
修复单引号、尾逗号、提取 JSON 块等，允许模型输出多余文本
绝不抛异常
"""

import json
import re
from typing import Any, Optional

# 提取可能的 JSON 块（{ ... }）
_BRACE_PATTERN = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)


def repair_json(text: str) -> Optional[dict]:
    """
    尝试从文本中提取并修复 JSON 为有效 dict
    - 修复单引号为双引号
    - 删除尾逗号
    - 提取 JSON 块
    - 允许模型多余文本
    - 绝不抛异常
    
    Returns:
        dict 若成功解析，否则 None
    """
    if not text or not isinstance(text, str):
        return None

    # 1. 找最外层的 { ... }
    candidates = _extract_json_candidates(text)
    for raw in candidates:
        fixed = _fix_json_string(raw)
        if fixed:
            result = _safe_parse(fixed)
            if result is not None:
                return result

    # 2. 整段尝试
    fixed = _fix_json_string(text.strip())
    if fixed:
        return _safe_parse(fixed)

    return None


def _extract_json_candidates(text: str) -> list:
    """提取可能的 JSON 对象块"""
    out = []
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start : i + 1])
                start = -1
    return out


def _fix_json_string(s: str) -> Optional[str]:
    """修复常见 JSON 问题"""
    if not s or not s.strip().startswith("{"):
        return None
    s = s.strip()
    # 先尝试直接解析
    if _safe_parse(s) is not None:
        return s
    # 删除尾逗号（, } 或 , ]）
    s = re.sub(r',(\s*[}\]])', r'\1', s)
    # 单引号 key: 'key' -> "key"
    s = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'\s*:", lambda m: '"' + m.group(1).replace('\\', '\\\\').replace('"', '\\"') + '":', s)
    # 单引号 value: : 'value'
    s = re.sub(r':\s*\'([^\'\\]*(?:\\.[^\'\\]*)*)\'', lambda m: ': "' + m.group(1).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"', s)
    return s


def _safe_parse(s: str) -> Optional[dict]:
    """安全解析，不抛异常"""
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None
