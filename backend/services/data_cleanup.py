"""
Data Directory Cleanup — Periodic stale file rotation

Manages disk usage for directories that grow unboundedly:
- task_store/checkpoints/ : completed task checkpoints (TTL: 7 days)
- traces/                 : LLM call traces per task (TTL: 7 days)
- usage_stats/            : daily usage JSONL (TTL: 30 days)
- episodes/               : episode memory (TTL: 14 days)

Already managed elsewhere (not touched here):
- duck_tasks/             : TTL cleanup in DuckTaskScheduler
- audit/                  : size-gated cleanup in AuditService
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"

# ── Retention policies (seconds) ──
_POLICIES = {
    "task_store/checkpoints": 7 * 86400,   # 7 days
    "traces":                 7 * 86400,   # 7 days
    "usage_stats":           30 * 86400,   # 30 days
    "episodes":              14 * 86400,   # 14 days
}

_CLEANUP_INTERVAL = 3600  # run every hour
_cleanup_task: Optional[asyncio.Task] = None


def _remove_stale_files(subdir: str, max_age: float) -> int:
    """Remove files older than *max_age* seconds under *_DATA_DIR / subdir*."""
    target = _DATA_DIR / subdir
    if not target.is_dir():
        return 0

    cutoff = time.time() - max_age
    removed = 0
    for entry in target.iterdir():
        if not entry.is_file():
            continue
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError as e:
            logger.debug(f"[data_cleanup] Cannot remove {entry}: {e}")
    return removed


async def run_cleanup_once():
    """Single pass: delete stale files in every managed directory."""
    loop = asyncio.get_running_loop()
    total = 0
    for subdir, max_age in _POLICIES.items():
        removed = await loop.run_in_executor(None, _remove_stale_files, subdir, max_age)
        if removed:
            logger.info(f"[data_cleanup] {subdir}: removed {removed} stale files")
            total += removed
    return total


def start_cleanup_loop():
    """Launch background periodic data cleanup (idempotent)."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        return

    async def _loop():
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL)
            try:
                await run_cleanup_once()
            except Exception as e:
                logger.warning(f"[data_cleanup] error: {e}")

    _cleanup_task = asyncio.create_task(_loop())
    logger.info("[data_cleanup] Periodic cleanup loop started (interval=1h)")


def stop_cleanup_loop():
    """Cancel the background cleanup task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
