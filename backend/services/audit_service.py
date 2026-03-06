"""
统一审计日志服务
全量记录 Agent 操作事件，支持按日分片存储、查询与自动清理。
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from paths import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

AUDIT_DIR = Path(DATA_DIR) / "audit"


def _ensure_dir():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _today_file() -> Path:
    return AUDIT_DIR / f"{date.today().isoformat()}.jsonl"


def append_audit_event(
    event_type: str,
    *,
    task_id: str = "",
    session_id: str = "",
    action_type: str = "",
    params_summary: str = "",
    result: str = "",
    risk_level: str = "low",
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """
    追加一条审计事件。返回事件 ID。
    event_type: action_execute | action_blocked | hitl_pending | hitl_approved |
                hitl_rejected | hitl_timeout | session_start | session_end |
                config_change | error
    """
    import app_state
    if not getattr(app_state, "ENABLE_AUDIT_LOG", True):
        return ""

    _ensure_dir()
    event_id = uuid.uuid4().hex[:16]
    event = {
        "id": event_id,
        "ts": datetime.now().isoformat(),
        "type": event_type,
        "task_id": task_id,
        "session_id": session_id,
        "action_type": action_type,
        "params_summary": params_summary[:500],
        "result": result,
        "risk_level": risk_level,
        "details": details or {},
    }
    try:
        path = _today_file()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Audit append failed: %s", e)
    return event_id


def query_audit_logs(
    *,
    event_type: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    查询审计日志，支持多维过滤。
    date_from / date_to: YYYY-MM-DD，用于限定日期范围。
    """
    _ensure_dir()
    results: List[Dict[str, Any]] = []

    files = sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True)
    for fpath in files:
        fname = fpath.stem  # YYYY-MM-DD
        if date_from and fname < date_from:
            continue
        if date_to and fname > date_to:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event_type and entry.get("type") != event_type:
                        continue
                    if task_id and entry.get("task_id") != task_id:
                        continue
                    if session_id and entry.get("session_id") != session_id:
                        continue
                    results.append(entry)
        except Exception:
            continue

    # 按时间倒序
    results.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return results[offset: offset + limit]


def get_audit_stats() -> Dict[str, Any]:
    """审计统计摘要"""
    _ensure_dir()
    total_events = 0
    type_counts: Dict[str, int] = {}
    total_size = 0
    file_count = 0

    for fpath in AUDIT_DIR.glob("*.jsonl"):
        file_count += 1
        total_size += fpath.stat().st_size
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        total_events += 1
                        t = entry.get("type", "unknown")
                        type_counts[t] = type_counts.get(t, 0) + 1
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return {
        "total_events": total_events,
        "type_counts": type_counts,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "file_count": file_count,
    }


def get_audit_event(log_id: str) -> Optional[Dict[str, Any]]:
    """按 ID 查找单条审计记录"""
    _ensure_dir()
    for fpath in AUDIT_DIR.glob("*.jsonl"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("id") == log_id:
                            return entry
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return None


def cleanup_old_logs() -> int:
    """
    清理超出磁盘配额的旧日志。返回删除的文件数。
    """
    import app_state
    max_mb = getattr(app_state, "AUDIT_LOG_MAX_SIZE_MB", 100)
    max_bytes = max_mb * 1024 * 1024
    _ensure_dir()

    files = sorted(AUDIT_DIR.glob("*.jsonl"))
    total_size = sum(f.stat().st_size for f in files)
    deleted = 0

    while total_size > max_bytes and files:
        oldest = files.pop(0)
        try:
            sz = oldest.stat().st_size
            oldest.unlink()
            total_size -= sz
            deleted += 1
        except Exception:
            continue
    return deleted
