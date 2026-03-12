"""
File Structure Summary Service — 方案 A+D

对大文件生成智能结构摘要，压缩后传给 LLM，避免全量注入。
首次解析后缓存为 {filename}_structure.md，后续直接读缓存。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from paths import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CACHE_DIR = Path(DATA_DIR) / "file_structure_cache"
# 超过此大小才使用摘要（字节）
BIG_FILE_THRESHOLD = 20 * 1024  # 20KB
# 摘要最大长度（字符）
SUMMARY_MAX_CHARS = 5000


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(file_path: str) -> str:
    """生成缓存文件名（基于路径 hash）"""
    abs_path = os.path.abspath(os.path.expanduser(file_path))
    h = hashlib.sha256(abs_path.encode()).hexdigest()[:16]
    return h


def _get_cache_path(file_path: str) -> Path:
    key = _cache_key(file_path)
    return CACHE_DIR / f"{key}_structure.md"


def get_file_structure_summary(file_path: str) -> Optional[str]:
    """
    获取文件结构摘要。优先读缓存；若文件过大且无缓存则生成并缓存。
    返回 None 表示文件较小或无需摘要，调用方可直接读全量。
    
    Returns:
        str: 结构摘要（如 CSS 变量、类名、HTML 骨架等），约 3-5KB
        None: 文件较小或不存在，直接读原文即可
    """
    try:
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.isfile(abs_path):
            return None
        
        size = os.path.getsize(abs_path)
        if size < BIG_FILE_THRESHOLD:
            return None  # 小文件直接读

        cache_path = _get_cache_path(abs_path)
        # 缓存有效：文件未修改
        if cache_path.exists():
            cache_mtime = cache_path.stat().st_mtime
            file_mtime = os.path.getmtime(abs_path)
            if cache_mtime >= file_mtime:
                try:
                    return cache_path.read_text(encoding="utf-8", errors="replace")[:SUMMARY_MAX_CHARS]
                except Exception as e:
                    logger.debug(f"Read cache failed: {e}")

        # 生成摘要
        summary = _generate_structure_summary(abs_path)
        if not summary:
            return None

        _ensure_cache_dir()
        cache_path.write_text(summary, encoding="utf-8")
        logger.info(f"File structure summary cached: {os.path.basename(abs_path)} -> {len(summary)} chars")
        return summary[:SUMMARY_MAX_CHARS]
    except Exception as e:
        logger.warning(f"File structure summary failed for {file_path}: {e}")
        return None


def _generate_structure_summary(file_path: str) -> Optional[str]:
    """提取文件结构：CSS 变量、类名、HTML 骨架、关键注释等"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        logger.warning(f"Cannot read file {file_path}: {e}")
        return None

    ext = os.path.splitext(file_path)[1].lower()
    parts = []

    if ext in (".html", ".htm"):
        # HTML: :root 变量、类名、标签结构
        parts.append(_extract_css_root(content))
        parts.append(_extract_html_classes(content))
        parts.append(_extract_html_structure(content))
        parts.append(_extract_key_comments(content))
    elif ext == ".css":
        parts.append(_extract_css_root(content))
        parts.append(_extract_css_selectors(content))
        parts.append(_extract_key_comments(content))
    elif ext in (".js", ".ts", ".tsx", ".jsx"):
        parts.append(_extract_js_functions(content))
        parts.append(_extract_key_comments(content))
    else:
        # 通用：前 100 行 + 行数
        lines = content.splitlines()
        parts.append(f"[文件类型: {ext}] 共 {len(lines)} 行")
        parts.append(f"[前 80 行]")
        parts.append("\n".join(lines[:80]))

    result = "\n\n".join(p for p in parts if p)
    return result[:SUMMARY_MAX_CHARS] if result else None


def _extract_css_root(content: str) -> str:
    """提取 :root 或 * 内的 CSS 变量"""
    m = re.search(r"(:root|html)\s*\{([^}]+)\}", content, re.DOTALL | re.IGNORECASE)
    if m:
        return f"[CSS 变量 :root]\n{m.group(2).strip()[:1500]}"
    # 匹配 -- 开头的变量
    vars = re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;]+)", content)
    if vars:
        return "[CSS 变量]\n" + "\n".join(f"  {k}: {v.strip()}" for k, v in vars[:30])
    return ""


def _extract_html_classes(content: str) -> str:
    """提取 class 名"""
    classes = re.findall(r'class\s*=\s*["\']([^"\']+)["\']', content)
    unique = list(dict.fromkeys(c.strip() for c in ",".join(classes).split() if c.strip()))[:50]
    if unique:
        return f"[HTML 类名] {', '.join(unique)}"
    return ""


def _extract_html_structure(content: str) -> str:
    """提取 HTML 骨架（主要标签层级）"""
    # 移除 script 内容
    no_script = re.sub(r"<script[^>]*>[\s\S]*?</script>", "<script>...</script>", content, flags=re.IGNORECASE)
    no_script = re.sub(r"<style[^>]*>[\s\S]*?</style>", "<style>...</style>", no_script, flags=re.IGNORECASE)
    tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*)?>", no_script)
    # 简化：只保留主要结构
    main_tags = [t for t in tags if t.lower() in ("html", "head", "body", "div", "main", "section", "header", "footer", "nav", "article", "aside", "form", "input", "button")][:40]
    if main_tags:
        return f"[HTML 结构] {' > '.join(main_tags)}"
    return ""


def _extract_css_selectors(content: str) -> str:
    """提取 CSS 选择器"""
    selectors = re.findall(r"([.#][a-zA-Z0-9_-]+[^{]*)\s*\{", content)
    unique = list(dict.fromkeys(s.strip()[:40] for s in selectors))[:50]
    if unique:
        return f"[CSS 选择器] {', '.join(unique)}"
    return ""


def _extract_js_functions(content: str) -> str:
    """提取 JS 函数名"""
    funcs = re.findall(r"function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(", content)
    funcs += re.findall(r"([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?(?:function|\()", content)
    unique = list(dict.fromkeys(funcs))[:40]
    if unique:
        return f"[JS 函数] {', '.join(unique)}"
    return ""


def _extract_key_comments(content: str) -> str:
    """提取关键注释"""
    comments = re.findall(r'(?:/\*[\s\S]*?\*/|//[^\n]*\n)', content)
    key = [c.strip()[:80] for c in comments if any(kw in c for kw in ("TODO", "FIXME", "NOTE", "重要", "关键", "设计"))][:10]
    if key:
        return f"[关键注释]\n" + "\n".join(key)
    return ""


def build_file_refs_with_summary(file_paths: list[str]) -> str:
    """
    为多个文件路径构建带摘要的引用文本。
    大文件用摘要替代，小文件直接给出路径。
    用于注入到 Duck 任务描述中。
    """
    if not file_paths:
        return ""
    parts = []
    for fp in file_paths:
        summary = get_file_structure_summary(fp)
        if summary:
            parts.append(f"【{os.path.basename(fp)}】\n{summary[:2500]}")
        else:
            parts.append(f"【{fp}】可直接读取")
    return "\n\n".join(parts)
