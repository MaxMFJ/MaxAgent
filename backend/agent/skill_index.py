"""
Skill Index — 从 VoltAgent/awesome-openclaw-skills 解析轻量索引，
供 LLM 快速了解可加载的在线技能，实现「索引优先 + 按需加载」。

索引格式：分类 + 技能名 + 一行描述，token 占用远小于全量 SKILL.md。
LLM 看到索引后可用 capsule find(task=...) 精确加载匹配技能。
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .capsule_loader import DEFAULT_CAPSULES_CACHE

logger = logging.getLogger(__name__)

AWESOME_README_URL = "https://raw.githubusercontent.com/VoltAgent/awesome-openclaw-skills/main/README.md"
SKILL_INDEX_FILENAME = "skill_index.json"
SKILLS_CACHE_DIR_NAME = "open_skills"

# 解析 markdown: - [skill-name](url) - description
_SKILL_LINE_RE = re.compile(r"^\s*-\s+\[([^\]]+)\]\([^)]+\)\s*-\s*(.+)$", re.M)
# 解析分类标题: ### Category Name 或 ## Category Name
_CATEGORY_RE = re.compile(r"^#{2,3}\s+(.+?)(?:\s*\((\d+)\))?\s*$", re.M)


def _parse_awesome_readme(text: str) -> Dict[str, Any]:
    """
    解析 awesome-openclaw-skills README，提取分类与技能列表。
    返回: { "categories": { "Coding": [{"name": "github", "desc": "..."}, ...], ... }, "total": N }
    """
    categories: Dict[str, List[Dict[str, str]]] = {}
    current_category = "General"
    total = 0

    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # 分类标题
        m_cat = _CATEGORY_RE.match(line_stripped)
        if m_cat:
            cat_name = m_cat.group(1).strip()
            # 跳过非技能分类（Table of Contents、Installation 等）
            skip = (
                "table of contents" in cat_name.lower()
                or "installation" in cat_name.lower()
                or "why this list" in cat_name.lower()
                or "security notice" in cat_name.lower()
                or "contributing" in cat_name.lower()
                or "license" in cat_name.lower()
                or "about" in cat_name.lower()
                or "openclaw deployment" in cat_name.lower()
            )
            if not skip:
                current_category = cat_name
                categories.setdefault(current_category, [])
            continue

        # 技能行: - [name](url) - desc
        m_skill = _SKILL_LINE_RE.match(line_stripped)
        if m_skill:
            name = m_skill.group(1).strip()
            desc = m_skill.group(2).strip()
            if len(desc) > 120:
                desc = desc[:117] + "..."
            categories.setdefault(current_category, []).append({"name": name, "desc": desc})
            total += 1

    return {"categories": categories, "total": total}


async def fetch_awesome_index() -> Optional[Dict[str, Any]]:
    """从 GitHub 拉取 awesome README 并解析为索引。"""
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(AWESOME_README_URL) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
    except Exception as e:
        logger.warning(f"Failed to fetch awesome index: {e}")
        return None

    return _parse_awesome_readme(text)


def get_skill_index_path(cache_dir: Optional[Path] = None) -> Path:
    """返回 skill_index.json 缓存路径。"""
    base = cache_dir or DEFAULT_CAPSULES_CACHE
    d = base / SKILLS_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / SKILL_INDEX_FILENAME


def load_cached_index(cache_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """从本地缓存加载索引。"""
    path = get_skill_index_path(cache_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"Failed to load skill index: {e}")
        return None


def save_index(data: Dict[str, Any], cache_dir: Optional[Path] = None) -> None:
    """保存索引到本地缓存。"""
    path = get_skill_index_path(cache_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def sync_skill_index(cache_dir: Optional[Path] = None) -> Tuple[bool, int]:
    """
    拉取 awesome 索引并缓存。
    返回 (success, total_skills)。
    """
    data = await fetch_awesome_index()
    if not data:
        return False, 0
    save_index(data, cache_dir)
    total = data.get("total", 0)
    logger.info(f"Skill index synced: {total} skills in {len(data.get('categories', {}))} categories")
    return True, total


def get_skill_index_for_prompt(
    max_chars: int = 1800,
    max_categories: int = 12,
    max_skills_per_category: int = 8,
    cache_dir: Optional[Path] = None,
) -> str:
    """
    生成供 LLM 使用的紧凑技能索引提示。
    格式: 分类 + 技能名列表，便于 LLM 快速了解可加载技能，再用 capsule find 精确匹配。
    """
    data = load_cached_index(cache_dir)
    if not data:
        return ""

    categories = data.get("categories", {})
    if not categories:
        return ""

    lines: List[str] = []
    lines.append("[在线技能索引] 以下为可加载的 OpenClaw 技能（按需用 capsule find(task=...) 搜索）：")
    total_shown = 0
    chars = len(lines[0]) + 2

    for i, (cat_name, skills) in enumerate(categories.items()):
        if i >= max_categories or chars >= max_chars:
            break
        if not skills:
            continue
        sample = skills[:max_skills_per_category]
        names = ", ".join(s["name"] for s in sample)
        if len(skills) > max_skills_per_category:
            names += f" 等{len(skills)}个"
        line = f"- {cat_name}: {names}"
        if chars + len(line) + 2 > max_chars:
            break
        lines.append(line)
        chars += len(line) + 2
        total_shown += len(skills)

    total = data.get("total", 0)
    lines.append(f"（共 {total} 技能，用 capsule find 按任务关键词匹配）")
    return "\n".join(lines)
