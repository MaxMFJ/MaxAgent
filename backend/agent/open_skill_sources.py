"""
Open Skill Sources — 内置的开源技能仓库列表与拉取逻辑。

作为第二策略（Strategy 2）：当 EvoMap 授权码不可用时，
从公开 GitHub 仓库拉取 Agent Skills（SKILL.md / skills.json）并转换为 SkillCapsule。

内置源：
  - anthropics/skills — Anthropic 官方示例技能
  - skillcreatorai/Ai-Agent-Skills — 社区技能集（47+）
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .capsule_loader import DEFAULT_CAPSULES_CACHE
from .skill_adapter import parse_skill_md, parse_skills_json

logger = logging.getLogger(__name__)

SKILLS_CACHE_DIR_NAME = "open_skills"

BUILTIN_SOURCES: List[Dict[str, Any]] = [
    {
        "id": "anthropic_skills",
        "name": "Anthropic Official Skills",
        "owner": "anthropics",
        "repo": "skills",
        "branch": "main",
        "path": "skills",
        "enabled": True,
        "description": "Anthropic 官方技能示例（PDF、文档、设计、开发等）",
    },
    {
        "id": "ai_agent_skills",
        "name": "AI Agent Skills (Community)",
        "owner": "skillcreatorai",
        "repo": "Ai-Agent-Skills",
        "branch": "main",
        "path": "skills",
        "enabled": True,
        "description": "社区技能集 — 47+ 技能涵盖开发、文档、创意、商务、效率",
    },
]


def get_skills_cache_dir(base: Optional[Path] = None) -> Path:
    d = (base or DEFAULT_CAPSULES_CACHE) / SKILLS_CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_sources_from_config() -> List[Dict[str, Any]]:
    """从 config/capsule_sources.json 读取 open_skill_sources 配置。"""
    config_path = Path(__file__).resolve().parent.parent / "config" / "capsule_sources.json"
    if not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("open_skill_sources", [])
    except Exception:
        return []


def get_enabled_sources(extra_sources: Optional[List[Dict]] = None) -> List[Dict[str, Any]]:
    """返回所有已启用的开源技能源（内置 + 配置文件 + 额外传入）。"""
    seen_ids = set()
    sources: List[Dict[str, Any]] = []

    for s in BUILTIN_SOURCES:
        if s.get("enabled", True) and s.get("id") not in seen_ids:
            sources.append(s)
            seen_ids.add(s.get("id"))

    for s in _load_sources_from_config():
        sid = s.get("id", "")
        if s.get("enabled", True) and sid and sid not in seen_ids:
            sources.append(s)
            seen_ids.add(sid)

    if extra_sources:
        for s in extra_sources:
            sid = s.get("id", "")
            if s.get("enabled", True) and sid and sid not in seen_ids:
                sources.append(s)
                seen_ids.add(sid)

    return sources


async def fetch_skill_md_from_github(
    owner: str,
    repo: str,
    path: str,
    branch: str = "main",
    token: str = "",
) -> List[Dict[str, Any]]:
    """
    通过 GitHub API 递归扫描仓库目录，找到所有 SKILL.md 文件并解析。
    返回 Capsule 字典列表。
    """
    results: List[Dict[str, Any]] = []
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    if branch:
        api_url += f"?ref={branch}"

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            capsules = await _scan_for_skills(session, api_url, f"github:{owner}/{repo}", 0)
            results.extend(capsules)
    except Exception as e:
        logger.warning(f"Failed to fetch skills from {owner}/{repo}: {e}")
        return []

    return results


async def _scan_for_skills(
    session: aiohttp.ClientSession,
    api_url: str,
    source_label: str,
    depth: int,
    max_depth: int = 4,
) -> List[Dict[str, Any]]:
    """递归扫描 GitHub 目录寻找 SKILL.md 和 skills.json。"""
    if depth > max_depth:
        return []

    try:
        async with session.get(api_url) as resp:
            if resp.status == 403:
                logger.warning("GitHub API rate limit — try setting GITHUB_TOKEN")
                return []
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception as e:
        logger.debug(f"GitHub API error: {e}")
        return []

    results: List[Dict[str, Any]] = []

    if not isinstance(data, list):
        return results

    for item in data:
        name = item.get("name", "")
        item_type = item.get("type", "")
        download_url = item.get("download_url", "")

        if item_type == "dir":
            sub_url = item.get("url", "")
            if sub_url:
                sub_caps = await _scan_for_skills(session, sub_url, source_label, depth + 1, max_depth)
                results.extend(sub_caps)

        elif item_type == "file" and name.lower() == "skill.md" and download_url:
            cap = await _fetch_and_parse_skill_md(session, download_url, source_label)
            if cap:
                results.append(cap)

        elif item_type == "file" and name.lower() == "skills.json" and download_url:
            caps = await _fetch_and_parse_skills_json(session, download_url, source_label)
            results.extend(caps)

    return results


async def _fetch_and_parse_skill_md(
    session: aiohttp.ClientSession,
    url: str,
    source_label: str,
) -> Optional[Dict[str, Any]]:
    """下载单个 SKILL.md 并解析为 Capsule 字典。"""
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
        cap = parse_skill_md(text, source=source_label)
        if cap:
            cap["_url"] = url
            logger.debug(f"Parsed skill: {cap.get('id', '?')} from {url}")
        return cap
    except Exception as e:
        logger.debug(f"Failed to parse SKILL.md from {url}: {e}")
        return None


async def _fetch_and_parse_skills_json(
    session: aiohttp.ClientSession,
    url: str,
    source_label: str,
) -> List[Dict[str, Any]]:
    """下载 skills.json 索引并解析。"""
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
        caps = parse_skills_json(data, source=source_label)
        logger.debug(f"Parsed skills.json from {url}: {len(caps)} skills")
        return caps
    except Exception as e:
        logger.debug(f"Failed to parse skills.json from {url}: {e}")
        return []


async def sync_open_skill_sources(
    cache_dir: Optional[Path] = None,
    sources: Optional[List[Dict]] = None,
    github_token: str = "",
) -> Dict[str, Any]:
    """
    从内置+自定义开源技能源拉取 SKILL.md 并缓存为 Capsule JSON。
    返回 { "synced": int, "failed": int, "sources": [...], "duration_ms": int }
    """
    cache = get_skills_cache_dir(cache_dir)
    try:
        from config.github_config import get_github_token
        token = github_token or get_github_token()
    except ImportError:
        token = github_token or os.environ.get("GITHUB_TOKEN", "")
    all_sources = get_enabled_sources(sources)
    start = time.time()

    result: Dict[str, Any] = {
        "synced": 0, "failed": 0, "total_skills": 0,
        "sources": [], "duration_ms": 0,
    }

    for src in all_sources:
        src_id = src.get("id", "unknown")
        owner = src.get("owner", "")
        repo = src.get("repo", "")
        branch = src.get("branch", "main")
        path = src.get("path", "")

        if not owner or not repo:
            continue

        result["sources"].append(src_id)
        try:
            capsules = await fetch_skill_md_from_github(owner, repo, path, branch, token)
            if capsules:
                src_dir = cache / src_id
                src_dir.mkdir(parents=True, exist_ok=True)
                for cap in capsules:
                    cid = cap.get("id", "unknown")
                    safe_name = f"{cid}.json".replace("/", "_")
                    out_path = src_dir / safe_name
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(cap, f, ensure_ascii=False, indent=2)
                result["synced"] += 1
                result["total_skills"] += len(capsules)
                logger.info(f"Open skills sync [{src_id}]: {len(capsules)} skills cached")
            else:
                result["failed"] += 1
                logger.debug(f"No skills found for {src_id}")
        except Exception as e:
            result["failed"] += 1
            logger.warning(f"Open skills sync [{src_id}] failed: {e}")

    result["duration_ms"] = int((time.time() - start) * 1000)
    return result


def load_cached_open_skills(cache_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """从本地缓存加载已同步的开源技能（Capsule 字典列表）。"""
    cache = get_skills_cache_dir(cache_dir)
    results: List[Dict[str, Any]] = []
    if not cache.exists():
        return results

    for json_file in sorted(cache.rglob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("id"):
                data.setdefault("source", f"open_skill:{json_file.parent.name}")
                results.append(data)
        except Exception:
            pass

    return results
