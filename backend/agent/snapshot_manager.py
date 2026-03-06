"""
Snapshot Manager — v3.4
在破坏性文件操作（write / delete / move）前自动保存快照，支持 undo 回滚。

存储位置: ~/.macagent/snapshots/<task_id>/<timestamp>_<uuid>.snap.json
每个快照记录原始内容（文件 ≤ 10 MB），允许通过 /rollback API 恢复。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SNAPSHOT_DIR = Path(os.path.expanduser("~/.macagent/snapshots"))
_MAX_FILE_SIZE = 10 * 1024 * 1024   # 10 MB — skip binary/large files
_MAX_SNAPSHOTS = 500                 # total cap; oldest pruned first


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SnapshotEntry:
    snapshot_id: str
    task_id: str
    session_id: str
    operation: str          # "write" | "delete" | "move" | "copy"
    path: str               # primary affected path
    destination: str        # destination path (for move/copy)
    original_content: Optional[str]  # file content before change (None = binary/large)
    original_existed: bool  # was the file present before?
    timestamp: float
    applied: bool = True    # False = already rolled back

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SnapshotEntry":
        return cls(**d)


# ---------------------------------------------------------------------------
# Core manager
# ---------------------------------------------------------------------------

class SnapshotManager:

    def __init__(self, snapshot_dir: Optional[Path] = None):
        self._dir = snapshot_dir or _SNAPSHOT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        operation: str,
        path: str,
        task_id: str = "",
        session_id: str = "",
        destination: str = "",
    ) -> Optional[SnapshotEntry]:
        """
        Capture a snapshot of *path* before a destructive operation.
        Returns the SnapshotEntry (persisted to disk) or None on error.
        """
        try:
            entry = self._build_entry(operation, path, task_id, session_id, destination)
            self._save(entry)
            self._prune()
            logger.debug("Snapshot captured: %s op=%s path=%s", entry.snapshot_id, operation, path)
            return entry
        except Exception as e:
            logger.warning("Snapshot capture failed (non-fatal): %s", e)
            return None

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Restore a previously captured snapshot.
        Returns {"success": bool, "message": str, "snapshot_id": str}.
        """
        entry = self._load(snapshot_id)
        if not entry:
            return {"success": False, "message": f"快照不存在: {snapshot_id}", "snapshot_id": snapshot_id}
        if not entry.applied:
            return {"success": False, "message": "该快照已回滚过", "snapshot_id": snapshot_id}

        try:
            msg = self._apply_rollback(entry)
            entry.applied = False
            self._save(entry)
            return {"success": True, "message": msg, "snapshot_id": snapshot_id}
        except Exception as e:
            logger.error("Rollback failed for %s: %s", snapshot_id, e)
            return {"success": False, "message": str(e), "snapshot_id": snapshot_id}

    def list_snapshots(
        self,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recent snapshots, optionally filtered by task/session."""
        entries = self._iter_all()
        if task_id:
            entries = [e for e in entries if e.task_id == task_id]
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return [e.to_dict() for e in entries[:limit]]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        path = self._path_for(snapshot_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_entry(
        self,
        operation: str,
        path: str,
        task_id: str,
        session_id: str,
        destination: str,
    ) -> SnapshotEntry:
        path_expanded = os.path.expanduser(path)
        existed = os.path.exists(path_expanded)
        content: Optional[str] = None

        if existed and os.path.isfile(path_expanded):
            size = os.path.getsize(path_expanded)
            if size <= _MAX_FILE_SIZE:
                try:
                    with open(path_expanded, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    content = None  # binary file

        return SnapshotEntry(
            snapshot_id=str(uuid.uuid4()),
            task_id=task_id,
            session_id=session_id,
            operation=operation,
            path=path_expanded,
            destination=os.path.expanduser(destination) if destination else "",
            original_content=content,
            original_existed=existed,
            timestamp=time.time(),
        )

    def _apply_rollback(self, entry: SnapshotEntry) -> str:
        op = entry.operation.lower()

        if op == "write":
            if not entry.original_existed:
                # File was newly created — delete it
                if os.path.exists(entry.path):
                    os.remove(entry.path)
                return f"已删除新建文件: {entry.path}"
            else:
                # File was overwritten — restore original content
                if entry.original_content is not None:
                    with open(entry.path, "w", encoding="utf-8") as f:
                        f.write(entry.original_content)
                    return f"已恢复文件内容: {entry.path}"
                return f"原始内容不可恢复（二进制或超大文件）: {entry.path}"

        elif op == "delete":
            if entry.original_content is not None and not os.path.exists(entry.path):
                parent = os.path.dirname(entry.path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(entry.path, "w", encoding="utf-8") as f:
                    f.write(entry.original_content)
                return f"已恢复已删除文件: {entry.path}"
            return f"无法恢复（内容未保存或文件已存在）: {entry.path}"

        elif op == "move":
            # Move back: destination → original path
            dest = entry.destination
            if dest and os.path.exists(dest):
                shutil.move(dest, entry.path)
                return f"已还原移动: {dest} → {entry.path}"
            return f"目标路径不存在，无法还原: {dest}"

        elif op == "copy":
            # Delete the copy
            if entry.destination and os.path.exists(entry.destination):
                if os.path.isdir(entry.destination):
                    shutil.rmtree(entry.destination)
                else:
                    os.remove(entry.destination)
                return f"已删除复制的文件: {entry.destination}"
            return f"复制目标不存在: {entry.destination}"

        return f"未知操作类型: {op}"

    def _save(self, entry: SnapshotEntry) -> None:
        path = self._path_for(entry.snapshot_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, ensure_ascii=False, indent=2)

    def _load(self, snapshot_id: str) -> Optional[SnapshotEntry]:
        path = self._path_for(snapshot_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return SnapshotEntry.from_dict(json.load(f))
        except Exception as e:
            logger.warning("Failed to load snapshot %s: %s", snapshot_id, e)
            return None

    def _path_for(self, snapshot_id: str) -> Path:
        return self._dir / f"{snapshot_id}.snap.json"

    def _iter_all(self) -> List[SnapshotEntry]:
        entries: List[SnapshotEntry] = []
        for p in self._dir.glob("*.snap.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    entries.append(SnapshotEntry.from_dict(json.load(f)))
            except Exception:
                pass
        return entries

    def _prune(self) -> None:
        """Keep at most _MAX_SNAPSHOTS snapshots; delete oldest first."""
        paths = sorted(self._dir.glob("*.snap.json"), key=lambda p: p.stat().st_mtime)
        if len(paths) > _MAX_SNAPSHOTS:
            for p in paths[: len(paths) - _MAX_SNAPSHOTS]:
                try:
                    p.unlink()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_snapshot_manager: Optional[SnapshotManager] = None


def get_snapshot_manager() -> SnapshotManager:
    global _snapshot_manager
    if _snapshot_manager is None:
        _snapshot_manager = SnapshotManager()
    return _snapshot_manager
