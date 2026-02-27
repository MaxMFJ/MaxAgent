"""
LLM 返回值兼容工具
用户可配置多种模型（Claude thinking、OpenAI、DeepSeek、Ollama 等），
各 API 返回的 content 格式不一，需统一提取为纯文本。
"""
from typing import Any


def extract_text_from_content(raw: Any) -> str:
    """
    从 LLM 返回的 content 中提取纯文本，兼容多种格式。

    支持的格式：
    - str: 直接返回
    - None: 返回 ""
    - list: 内容块列表（Claude thinking、Anthropic、部分网关）
      - [{"type":"text","text":"..."}]
      - [{"type":"thinking","thinking":"..."},{"type":"text","text":"..."}]
      - [{"type":"input_text","text":"..."}]
    - dict: 单块 {"type":"text","text":"..."} 或 {"text":"..."}
    - 其他: str(raw) 兜底
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if not isinstance(block, dict):
                if isinstance(block, str):
                    parts.append(block)
                continue
            t = block.get("type")
            if t == "text" and "text" in block:
                parts.append(block.get("text") or "")
            elif t == "input_text" and "text" in block:
                parts.append(block.get("text") or "")
            elif t == "thinking":
                pass  # 忽略 thinking 块
            elif "text" in block:
                parts.append(block.get("text") or "")
        return "".join(parts) if parts else ""
    if isinstance(raw, dict):
        if "text" in raw:
            return raw.get("text") or ""
        if raw.get("type") == "text" and "text" in raw:
            return raw.get("text") or ""
    try:
        return str(raw) if raw else ""
    except Exception:
        return ""
