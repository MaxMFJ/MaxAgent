"""
Runtime Journal — Append-only task execution log (v2.2)

JSON lines format. Each entry records a state transition.
Used for crash recovery: rebuild in-memory state from journal.

Events:
  TASK_CREATED, TASK_ENQUEUED, TASK_ASSIGNED,
  TASK_RUNNING, TASK_COMPLETED, TASK_FAILED,
  TASK_REQUEUED, LEASE_EXPIRED, DAG_CREATED, DAG_COMPLETED

No external DB. Append-only file IO via asyncio executor.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Journal file path
_DATA_DIR = Path(__file__).parent.parent / "data"
_JOURNAL_FILE = _DATA_DIR / "runtime_journal.log"

# Event types
TASK_CREATED = "TASK_CREATED"
TASK_ENQUEUED = "TASK_ENQUEUED"
TASK_ASSIGNED = "TASK_ASSIGNED"
TASK_RUNNING = "TASK_RUNNING"
TASK_COMPLETED = "TASK_COMPLETED"
TASK_FAILED = "TASK_FAILED"
TASK_FAILED_TEMP = "TASK_FAILED_TEMP"
TASK_REQUEUED = "TASK_REQUEUED"
TASK_CANCELLED = "TASK_CANCELLED"
LEASE_EXPIRED = "LEASE_EXPIRED"
DAG_CREATED = "DAG_CREATED"
DAG_COMPLETED = "DAG_COMPLETED"


class RuntimeJournal:
    """Append-only journal for task state transitions"""

    _instance: Optional["RuntimeJournal"] = None

    def __init__(self):
        self._file_path = _JOURNAL_FILE
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        _DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "RuntimeJournal":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def append(
        self,
        event: str,
        task_id: str = "",
        dag_id: str = "",
        duck_id: str = "",
        node_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ):
        """Append a journal entry (non-blocking via executor)"""
        entry = {
            "ts": time.time(),
            "event": event,
            "task_id": task_id,
            "dag_id": dag_id,
            "duck_id": duck_id,
            "node_id": node_id,
        }
        if extra:
            entry["extra"] = extra

        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"

        loop = self._loop or asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._write_line, line)
        except Exception as e:
            logger.warning(f"[journal] Failed to append: {e}")

    def _write_line(self, line: str):
        """Sync append (runs in executor thread)"""
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.write(line)

    def read_all(self) -> List[Dict]:
        """Read all journal entries (for crash recovery)"""
        entries = []
        if not self._file_path.exists():
            return entries
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning(f"[journal] Corrupt entry at line {line_num}")
        except Exception as e:
            logger.error(f"[journal] Failed to read: {e}")
        return entries

    def rotate(self, max_size_mb: float = 10.0):
        """Rotate journal if it exceeds max size"""
        try:
            if not self._file_path.exists():
                return
            size_mb = self._file_path.stat().st_size / (1024 * 1024)
            if size_mb > max_size_mb:
                backup = self._file_path.with_suffix(".log.old")
                if backup.exists():
                    backup.unlink()
                self._file_path.rename(backup)
                logger.info(f"[journal] Rotated ({size_mb:.1f}MB → {backup.name})")
        except Exception as e:
            logger.warning(f"[journal] Rotation failed: {e}")

    def truncate(self):
        """Clear journal (after successful recovery)"""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                f.write("")
            logger.info("[journal] Truncated after recovery")
        except Exception as e:
            logger.warning(f"[journal] Truncate failed: {e}")


# ─── Crash Recovery ──────────────────────────────────

async def recover_runtime_state() -> Dict[str, Any]:
    """
    从 journal 恢复运行时状态:
    - 重建 task 状态
    - 返回需要 re-queue 的 task_ids
    - 返回已完成的 task_ids (跳过)

    返回 dict:
      completed_task_ids: set
      requeue_task_ids: set
      dag_states: dict[dag_id -> status]
      stats: dict
    """
    journal = RuntimeJournal.get_instance()
    entries = journal.read_all()

    if not entries:
        return {"completed_task_ids": set(), "requeue_task_ids": set(),
                "dag_states": {}, "stats": {"entries": 0}}

    # 每个 task 的最终状态
    task_last_state: Dict[str, str] = {}
    dag_last_state: Dict[str, str] = {}

    for entry in entries:
        task_id = entry.get("task_id", "")
        event = entry.get("event", "")
        dag_id = entry.get("dag_id", "")

        if task_id and event.startswith("TASK_"):
            task_last_state[task_id] = event

        if dag_id and event.startswith("DAG_"):
            dag_last_state[dag_id] = event

    # 分类
    completed = set()
    requeue = set()

    for task_id, last_event in task_last_state.items():
        if last_event in (TASK_COMPLETED, TASK_FAILED, TASK_CANCELLED):
            completed.add(task_id)
        elif last_event in (TASK_ASSIGNED, TASK_RUNNING, TASK_ENQUEUED):
            # 崩溃时在执行中 → 需要重新排队
            requeue.add(task_id)

    logger.info(
        f"[recovery] Journal: {len(entries)} entries, "
        f"completed={len(completed)}, requeue={len(requeue)}, "
        f"dags={len(dag_last_state)}"
    )

    return {
        "completed_task_ids": completed,
        "requeue_task_ids": requeue,
        "dag_states": dag_last_state,
        "stats": {"entries": len(entries), "completed": len(completed), "requeue": len(requeue)},
    }


def get_journal() -> RuntimeJournal:
    return RuntimeJournal.get_instance()


# ─── Journal Compaction (v2.3) ───────────────────────

def _compact_journal_sync():
    """
    Compact journal: keep only the latest event per task/DAG.
    Crash-safe: write to temp file, then atomic rename.
    """
    journal = RuntimeJournal.get_instance()
    file_path = journal._file_path

    if not file_path.exists():
        return

    try:
        size_before = file_path.stat().st_size
        if size_before < 1024:  # < 1KB, skip
            return

        entries = journal.read_all()
        if not entries:
            return

        # Keep only the latest event per (task_id or dag_id)
        task_latest: Dict[str, dict] = {}
        dag_latest: Dict[str, dict] = {}

        for entry in entries:
            task_id = entry.get("task_id", "")
            dag_id = entry.get("dag_id", "")
            event = entry.get("event", "")

            if task_id and event.startswith("TASK_"):
                task_latest[task_id] = entry
            if dag_id and event.startswith("DAG_"):
                dag_latest[dag_id] = entry

        # Merge into compacted list
        compacted = list(task_latest.values()) + list(dag_latest.values())
        compacted.sort(key=lambda e: e.get("ts", 0))

        # Write to temp file
        temp_path = file_path.with_suffix(".log.compact.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            for entry in compacted:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        # Atomic replace (POSIX rename is atomic on same filesystem)
        temp_path.replace(file_path)

        size_after = file_path.stat().st_size
        logger.info(
            f"[journal_compaction] {len(entries)} → {len(compacted)} entries, "
            f"{size_before / 1024:.1f}KB → {size_after / 1024:.1f}KB"
        )
    except Exception as e:
        logger.warning(f"[journal_compaction] Failed: {e}")


# ─── Periodic Compaction Loop ────────────────────────
_compaction_task = None


async def _compaction_loop(interval: float = 600.0):
    """Every 10 minutes, compact the journal via executor (non-blocking)"""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(interval)
        try:
            await loop.run_in_executor(None, _compact_journal_sync)
        except Exception as e:
            logger.warning(f"[journal_compaction] Loop error: {e}")


def start_journal_compaction_loop(interval: float = 600.0):
    """Start periodic journal compaction (10 min default)"""
    global _compaction_task
    if _compaction_task is not None:
        return
    _compaction_task = asyncio.create_task(_compaction_loop(interval))
    logger.info(f"[journal_compaction] Loop started (interval={interval}s)")
