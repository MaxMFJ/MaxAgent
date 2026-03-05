"""
Capsule On-Demand Fetch — 按需拉取技能。

核心思路：
  1. 先查本地已注册 CapsuleRegistry（毫秒级，无网络）
  2. 命中 → 直接返回
  3. 未命中 → 查 skill_index 轻量索引，找到最相关的技能
  4. 对匹配条目：通过 open_skill_sources 拉取对应 SKILL.md（单文件 HTTP，秒级）
  5. 解析 → 写入缓存 → 注册到 CapsuleRegistry
  6. 返回刚加载的 Capsule 列表

与旧「全量同步」的区别：
  - 旧：启动时批量拉取全部 GitHub 技能（数百个 HTTP 请求，分钟级）
  - 新：首次请求时按需单文件拉取（1~3 个 HTTP 请求，秒级）

FeatureFlag: ENABLE_ON_DEMAND_SKILL_FETCH（默认 True，可置 False 退回全量同步）
"""

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .capsule_loader import DEFAULT_CAPSULES_CACHE
from .capsule_registry import get_capsule_registry
from .capsule_validator import validate_capsules
from .skill_index import (
    load_cached_index,
    sync_skill_index,
    get_skill_index_path,
)
from .open_skill_sources import (
    get_skills_cache_dir,
    SKILLS_CACHE_DIR_NAME,
)
from .skill_adapter import parse_skill_md

logger = logging.getLogger(__name__)

# ── 在线技能库 GitHub 根路径配置 ═══════════════════════════════════════════════
# 格式：{ "source_id": { "owner", "repo", "branch", "skills_root", "raw_base" } }
_SKILL_REPOS: Dict[str, Dict[str, str]] = {
    "openclaw_skills": {
        "owner": "openclaw",
        "repo": "skills",
        "branch": "main",
        "skills_root": "skills",
        "raw_base": "https://raw.githubusercontent.com/openclaw/skills/main/skills",
    },
    "ai_agent_skills": {
        "owner": "skillcreatorai",
        "repo": "Ai-Agent-Skills",
        "branch": "main",
        "skills_root": "skills",
        "raw_base": "https://raw.githubusercontent.com/skillcreatorai/Ai-Agent-Skills/main/skills",
    },
    "anthropic_skills": {
        "owner": "anthropics",
        "repo": "skills",
        "branch": "main",
        "skills_root": "skills",
        "raw_base": "https://raw.githubusercontent.com/anthropics/skills/main/skills",
    },
}

# 最大单次按需拉取数量
MAX_FETCH_PER_REQUEST = 3

# 按需拉取结果本地内存缓存（避免同一会话重复拉取）
_fetch_cache: Dict[str, List[Dict[str, Any]]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════════════════════

async def search_and_fetch(
    task_description: str,
    limit: int = 3,
    min_score: float = 0.5,
    cache_dir: Optional[Path] = None,
    github_token: str = "",
    force_remote: bool = False,
) -> List[Any]:
    """
    按任务描述搜索技能，按需从 GitHub 拉取缺失技能。

    流程：
      1. 本地注册表搜索
      2. 如本地结果不足 → 查 skill_index 索引 → 按需拉取
      3. 新加载的技能注册到 CapsuleRegistry 并缓存

    Args:
        task_description: 任务描述（中文/英文）
        limit: 最多返回条数
        min_score: 本地注册表最低匹配分
        cache_dir: 缓存目录（默认 DEFAULT_CAPSULES_CACHE）
        github_token: GitHub Token（提高 API 限速）
        force_remote: 为 True 时跳过本地注册表，直接查索引拉取

    Returns:
        SkillCapsule 列表（可能混合本地已有 + 刚拉取的）
    """
    cache_dir = cache_dir or DEFAULT_CAPSULES_CACHE

    # ── 步骤 1：本地注册表快速查找 ─────────────────────────────────────────────
    registry = get_capsule_registry()
    local_results = []
    if not force_remote:
        local_results = registry.find_capsule_by_task(task_description, limit=limit, min_score=min_score)
        if len(local_results) >= limit:
            logger.debug(f"On-demand: local hit ({len(local_results)}) for '{task_description[:40]}'")
            return local_results

    shortage = limit - len(local_results)
    local_ids = {c.id for c in local_results}

    # ── 步骤 2：确保 skill_index 已加载 ──────────────────────────────────────
    index = load_cached_index(cache_dir)
    if not index:
        logger.info("On-demand: skill index not found, fetching...")
        ok, total = await sync_skill_index(cache_dir)
        index = load_cached_index(cache_dir) if ok else None

    if not index:
        logger.warning("On-demand: skill index unavailable, returning local only")
        return local_results

    # ── 步骤 3：从索引匹配候选技能名 ──────────────────────────────────────────
    candidates = _match_index(task_description, index, top_n=shortage * 2)
    if not candidates:
        return local_results

    # ── 步骤 4：按需拉取（跳过已缓存 / 已注册的）─────────────────────────────
    token = github_token or os.environ.get("GITHUB_TOKEN", "")
    try:
        from config.github_config import get_github_token
        token = token or get_github_token()
    except Exception:
        pass

    newly_loaded = await _fetch_skills_by_names(
        candidates[:MAX_FETCH_PER_REQUEST],
        cache_dir=cache_dir,
        github_token=token,
        skip_ids=local_ids,
    )

    # ── 步骤 5：注册新技能 ──────────────────────────────────────────────────
    if newly_loaded:
        validated = validate_capsules(newly_loaded, allow_gep_conversion=True, check_safety=True)
        registry.register_many(validated)
        # 从注册表取回已注册对象
        for v in validated:
            cap = registry.get_capsule(v.id)
            if cap and cap.id not in local_ids:
                local_results.append(cap)
                local_ids.add(cap.id)
                if len(local_results) >= limit:
                    break

    return local_results[:limit]


async def prefetch_skills_for_task(
    task_description: str,
    cache_dir: Optional[Path] = None,
    github_token: str = "",
) -> int:
    """
    后台预拉取（fire-and-forget）：在任务开始时异步拉取可能需要的技能。
    不阻塞主流程，拉取完成后自动注册。
    Returns: 本次拉取并注册的新技能数
    """
    try:
        new_caps = await search_and_fetch(
            task_description,
            limit=MAX_FETCH_PER_REQUEST,
            cache_dir=cache_dir,
            github_token=github_token,
        )
        return len(new_caps)
    except Exception as e:
        logger.debug(f"prefetch_skills_for_task error: {e}")
        return 0


def is_on_demand_enabled() -> bool:
    """读取 FeatureFlag ENABLE_ON_DEMAND_SKILL_FETCH（默认 True）。"""
    try:
        from app_state import ENABLE_ON_DEMAND_SKILL_FETCH
        return bool(ENABLE_ON_DEMAND_SKILL_FETCH)
    except ImportError:
        pass
    return os.environ.get("MACAGENT_ENABLE_ON_DEMAND_SKILL_FETCH", "true").lower() not in ("false", "0", "no")


# ═══════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _match_index(task: str, index: Dict[str, Any], top_n: int = 6) -> List[str]:
    """
    在 skill_index 中按任务关键词打分，返回最相关的技能名列表。
    评分：名称匹配 +2，描述匹配 +1，短词加分。
    """
    task_lower = task.lower()
    # 中英文关键词提取
    keywords = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", task_lower))
    # 移除常见停用词
    stop = {"the", "and", "for", "with", "this", "that", "from", "using",
            "的", "了", "在", "是", "我", "要", "请", "把", "用", "和", "一"}
    keywords -= stop

    scored: Dict[str, float] = {}
    categories = index.get("categories", {})

    for cat_name, skills in categories.items():
        cat_lower = cat_name.lower()
        cat_bonus = sum(1.0 for kw in keywords if kw in cat_lower) * 0.3

        for skill in skills:
            name = skill.get("name", "")
            desc = skill.get("desc", "")
            name_lower = name.lower()
            desc_lower = desc.lower()

            score = cat_bonus
            for kw in keywords:
                if kw in name_lower:
                    score += 2.0
                if kw in desc_lower:
                    score += 1.0

            if score > 0:
                scored[name] = max(scored.get(name, 0), score)

    ranked = sorted(scored.items(), key=lambda x: -x[1])
    return [name for name, _ in ranked[:top_n]]


async def _fetch_skills_by_names(
    skill_names: List[str],
    cache_dir: Path,
    github_token: str = "",
    skip_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """
    按技能名在配置的 GitHub 仓库中拉取对应的 SKILL.md。
    每个名称仅拉取一次（优先从本地文件系统缓存检查）。
    """
    skip_ids = skip_ids or set()
    results: List[Dict[str, Any]] = []

    skills_cache = get_skills_cache_dir(cache_dir)
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        tasks = [
            _fetch_single_skill(session, name, skills_cache, skip_ids)
            for name in skill_names
        ]
        sub_results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in sub_results:
        if isinstance(r, list):
            results.extend(r)
        elif isinstance(r, Exception):
            logger.debug(f"Skill fetch error: {r}")

    return results


async def _fetch_single_skill(
    session: aiohttp.ClientSession,
    skill_name: str,
    skills_cache: Path,
    skip_ids: set,
) -> List[Dict[str, Any]]:
    """
    按技能名尝试各仓库拉取 SKILL.md。
    先检查本地磁盘缓存，无则发 HTTP 请求。
    """
    # 标准化技能名用于路径
    clean_name = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]", "-", skill_name).lower()

    # 检查磁盘缓存
    for src_id in _SKILL_REPOS:
        cached_path = skills_cache / src_id / f"{clean_name}.json"
        if cached_path.exists():
            try:
                with open(cached_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("id") and data["id"] not in skip_ids:
                    logger.debug(f"On-demand: disk cache hit for '{skill_name}' ({src_id})")
                    return [data]
            except Exception:
                pass

    # 内存缓存
    cache_key = skill_name.lower()
    if cache_key in _fetch_cache:
        cached = [c for c in _fetch_cache[cache_key] if c.get("id") not in skip_ids]
        if cached:
            return cached

    # 按序尝试仓库拉取（优先最全的仓库）
    for src_id, repo_cfg in _SKILL_REPOS.items():
        raw_base = repo_cfg["raw_base"]
        # 尝试常见路径格式
        candidate_urls = [
            f"{raw_base}/{skill_name}/SKILL.md",
            f"{raw_base}/{skill_name.lower()}/SKILL.md",
            f"{raw_base}/{clean_name}/SKILL.md",
        ]

        for url in candidate_urls:
            cap = await _try_fetch_skill_md(session, url, src_id)
            if cap and cap.get("id") and cap["id"] not in skip_ids:
                # 写磁盘缓存
                dest_dir = skills_cache / src_id
                dest_dir.mkdir(parents=True, exist_ok=True)
                cid = cap["id"]
                out_path = dest_dir / f"{cid}.json".replace("/", "_")
                try:
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(cap, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                _fetch_cache[cache_key] = [cap]
                logger.info(f"On-demand: fetched '{skill_name}' from {src_id} ({url})")
                return [cap]

    logger.debug(f"On-demand: '{skill_name}' not found in any repo")
    return []


async def _try_fetch_skill_md(
    session: aiohttp.ClientSession,
    url: str,
    source_label: str,
) -> Optional[Dict[str, Any]]:
    """GET 单个 SKILL.md URL 并解析。HTTP 404 静默跳过。"""
    try:
        async with session.get(url) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                logger.debug(f"On-demand HTTP {resp.status}: {url}")
                return None
            text = await resp.text()
        cap = parse_skill_md(text, source=f"on_demand:{source_label}")
        if cap:
            cap["_url"] = url
        return cap
    except asyncio.TimeoutError:
        logger.debug(f"On-demand timeout: {url}")
        return None
    except Exception as e:
        logger.debug(f"On-demand fetch error ({url}): {e}")
        return None


def clear_fetch_cache() -> None:
    """清空内存缓存（用于测试或热重载）。"""
    _fetch_cache.clear()
