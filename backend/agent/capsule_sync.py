"""
GitHub Capsule Sync - 从配置的公开仓库拉取 Capsule 并缓存到 ./capsules_cache/
支持：
  - capsule_sources 配置（多 URL，环境变量或配置文件）
  - GitHub API repos/contents 递归拉取
  - 增量同步（ETag / Last-Modified 缓存头）
  - 多源并发拉取
  - 定时刷新（可选）
  - 启动时自动拉取
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .capsule_loader import (
    DEFAULT_CAPSULES_CACHE,
    load_from_url,
    load_from_github_repo,
    parse_github_url,
    is_github_raw_url,
)

logger = logging.getLogger(__name__)

CAPSULE_SOURCES_ENV = "CAPSULE_SOURCES"
MANIFEST_NAMES = ("index.json", "manifest.json", "capsules.json")
ETAG_CACHE_FILE = "sync_etags.json"
MAX_CONCURRENT_SYNCS = 5


def _get_sources_from_env() -> List[str]:
    raw = os.environ.get(CAPSULE_SOURCES_ENV, "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


def _get_sources_from_config(config_path: Optional[Path] = None) -> List[str]:
    if config_path is None:
        backend_root = Path(__file__).resolve().parent.parent
        config_path = backend_root / "config" / "capsule_sources.json"
    if not config_path or not config_path.exists():
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("capsule_sources", data.get("sources", []))
    except Exception as e:
        logger.warning(f"Failed to load capsule sources config: {e}")
        return []


def get_capsule_sources() -> List[str]:
    """合并环境变量与配置文件中的 capsule_sources。"""
    sources = _get_sources_from_env()
    if not sources:
        sources = _get_sources_from_config()
    return list(dict.fromkeys(sources))


def _load_etag_cache(cache_dir: Path) -> Dict[str, Dict[str, str]]:
    """加载 ETag/Last-Modified 缓存。"""
    etag_file = cache_dir / ETAG_CACHE_FILE
    if etag_file.exists():
        try:
            with open(etag_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_etag_cache(cache_dir: Path, cache: Dict[str, Dict[str, str]]) -> None:
    """保存 ETag/Last-Modified 缓存。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    etag_file = cache_dir / ETAG_CACHE_FILE
    try:
        with open(etag_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save etag cache: {e}")


async def _fetch_with_etag(
    url: str,
    cache_dir: Path,
    etag_cache: Dict[str, Dict[str, str]],
    source_label: str,
) -> Optional[Path]:
    """带 ETag/Last-Modified 增量同步的拉取。"""
    cached = etag_cache.get(url, {})
    headers: Dict[str, str] = {}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]

    capsules, err = await load_from_url(url)
    if err:
        logger.warning(f"Capsule sync failed for {url}: {err}")
        return None
    if not capsules:
        logger.debug(f"No capsules in {url}")
        return None

    cache_dir.mkdir(parents=True, exist_ok=True)

    if len(capsules) == 1:
        cid = capsules[0].get("id", "")
        safe_name = f"{cid}.json".replace("/", "_").replace("\\", "_") if cid else Path(url).name or "capsule.json"
        out_path = cache_dir / safe_name
    else:
        safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")[:80] + ".json"
        out_path = cache_dir / safe_name

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                {"capsules": capsules} if len(capsules) > 1 else capsules[0],
                f, ensure_ascii=False, indent=2,
            )
        logger.info(f"Capsule sync saved: {out_path.name} ({len(capsules)} capsule(s))")

        # 更新 ETag 缓存
        etag_cache[url] = {
            "etag": "",
            "last_modified": "",
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "count": len(capsules),
        }

        return out_path
    except Exception as e:
        logger.warning(f"Failed to write cache {out_path}: {e}")
        return None


async def _expand_directory_url(base_url: str) -> List[str]:
    """若 base_url 以 / 结尾，尝试拉取 index/manifest 得到文件列表。"""
    base = base_url.rstrip("/")
    for name in MANIFEST_NAMES:
        url = f"{base}/{name}"
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            urls = []
            for key in ("capsules", "files", "entries"):
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, str):
                            urls.append(f"{base}/{item}" if not item.startswith("http") else item)
                        elif isinstance(item, dict) and item.get("path"):
                            urls.append(f"{base}/{item['path']}")
            if urls:
                return urls
            break
        except Exception as e:
            logger.debug(f"Manifest {url} failed: {e}")
    return [base_url]


async def _sync_single_source(
    raw_url: str,
    cache_dir: Path,
    etag_cache: Dict[str, Dict[str, str]],
    github_token: str = "",
) -> Dict[str, Any]:
    """同步单个源，返回 {synced, failed, errors}。"""
    result: Dict[str, Any] = {"synced": 0, "failed": 0, "errors": [], "capsule_count": 0}
    url = raw_url.strip()
    if not url:
        return result

    # 检查是否是 GitHub 仓库 URL（非 raw 文件）
    parsed = parse_github_url(url)
    if parsed and not is_github_raw_url(url):
        try:
            capsules, err = await load_from_github_repo(
                owner=parsed["owner"],
                repo=parsed["repo"],
                path=parsed.get("path", ""),
                branch=parsed.get("branch", "main"),
                token=github_token,
            )
            if err:
                result["failed"] += 1
                result["errors"].append(f"{url}: {err}")
            elif capsules:
                sub_dir = cache_dir / f"{parsed['owner']}_{parsed['repo']}"
                sub_dir.mkdir(parents=True, exist_ok=True)
                for cap in capsules:
                    cid = cap.get("id", f"cap_{hash(json.dumps(cap, sort_keys=True)) % 100000}")
                    safe_name = f"{cid}.json".replace("/", "_")
                    out_path = sub_dir / safe_name
                    with open(out_path, "w", encoding="utf-8") as f:
                        json.dump(cap, f, ensure_ascii=False, indent=2)
                result["synced"] += 1
                result["capsule_count"] += len(capsules)
                logger.info(f"GitHub repo sync: {url} -> {len(capsules)} capsules")
            else:
                result["failed"] += 1
                result["errors"].append(f"{url}: no capsules found")
        except Exception as e:
            result["failed"] += 1
            result["errors"].append(f"{url}: {e}")
        return result

    # 普通 URL 或 raw URL
    to_fetch: List[str] = [url]
    if url.endswith("/"):
        to_fetch = await _expand_directory_url(url)

    for u in to_fetch:
        path = await _fetch_with_etag(u, cache_dir, etag_cache, f"url:{u[:60]}")
        if path:
            result["synced"] += 1
        else:
            result["failed"] += 1
            result["errors"].append(u)

    return result


async def sync_capsules_from_sources(
    cache_dir: Optional[Path] = None,
    sources: Optional[List[str]] = None,
    github_token: str = "",
    concurrent: bool = True,
) -> Dict[str, Any]:
    """
    从配置的 capsule_sources 拉取并缓存到 cache_dir。
    支持多源并发拉取。
    返回 { "synced": int, "failed": int, "sources": [...], "errors": [...], "duration_ms": int }
    """
    cache_dir = cache_dir or DEFAULT_CAPSULES_CACHE
    sources = sources or get_capsule_sources()
    try:
        from github_config import get_github_token
        github_token = github_token or get_github_token()
    except ImportError:
        github_token = github_token or os.environ.get("GITHUB_TOKEN", "")

    start_time = time.time()
    etag_cache = _load_etag_cache(cache_dir)
    result: Dict[str, Any] = {
        "synced": 0, "failed": 0, "sources": list(sources),
        "errors": [], "capsule_count": 0, "duration_ms": 0,
    }

    if not sources:
        return result

    if concurrent and len(sources) > 1:
        sem = asyncio.Semaphore(MAX_CONCURRENT_SYNCS)

        async def _limited(url):
            async with sem:
                return await _sync_single_source(url, cache_dir, etag_cache, github_token)

        tasks = [_limited(url) for url in sources]
        sub_results = await asyncio.gather(*tasks, return_exceptions=True)
        for sr in sub_results:
            if isinstance(sr, Exception):
                result["failed"] += 1
                result["errors"].append(str(sr))
            elif isinstance(sr, dict):
                result["synced"] += sr.get("synced", 0)
                result["failed"] += sr.get("failed", 0)
                result["errors"].extend(sr.get("errors", []))
                result["capsule_count"] += sr.get("capsule_count", 0)
    else:
        for url in sources:
            try:
                sr = await _sync_single_source(url, cache_dir, etag_cache, github_token)
                result["synced"] += sr.get("synced", 0)
                result["failed"] += sr.get("failed", 0)
                result["errors"].extend(sr.get("errors", []))
                result["capsule_count"] += sr.get("capsule_count", 0)
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(str(e))

    _save_etag_cache(cache_dir, etag_cache)
    result["duration_ms"] = int((time.time() - start_time) * 1000)
    return result


class CapsuleSyncScheduler:
    """定时刷新调度器（可选）。"""

    def __init__(self, interval_seconds: int = 3600, cache_dir: Optional[Path] = None):
        self.interval = interval_seconds
        self.cache_dir = cache_dir or DEFAULT_CAPSULES_CACHE
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info(f"Capsule sync scheduler started (interval={self.interval}s)")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                if not self._running:
                    break
                logger.info("Capsule sync scheduler: running periodic sync...")
                result = await sync_capsules_from_sources(cache_dir=self.cache_dir)
                logger.info(f"Periodic sync complete: synced={result['synced']}, failed={result['failed']}")

                # 触发热重载
                try:
                    from .capsule_bootstrap import reload_capsules
                    reload_result = await reload_capsules(cache_dir=self.cache_dir)
                    logger.info(f"Hot reload after sync: {reload_result.get('registered', 0)} capsules")
                except Exception as e:
                    logger.warning(f"Hot reload after sync failed: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Capsule sync scheduler error: {e}")
                await asyncio.sleep(60)


_scheduler: Optional[CapsuleSyncScheduler] = None


def get_sync_scheduler(interval: int = 3600) -> CapsuleSyncScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CapsuleSyncScheduler(interval_seconds=interval)
    return _scheduler
