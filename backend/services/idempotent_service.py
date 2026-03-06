"""
幂等任务服务
相同 (action_type + params) 的执行结果缓存，避免重复执行。
只缓存成功的只读/安全操作结果，run_shell/create_and_run_script 等副作用操作不缓存。
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from paths import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CACHE_DIR = Path(DATA_DIR) / "task_cache"

# 不允许缓存的动作类型（有副作用）
_NON_CACHEABLE_ACTIONS = frozenset({
    "run_shell",
    "create_and_run_script",
    "delete_file",
    "move_file",
    "write_file",
    "copy_file",
})


def _ensure_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _compute_hash(action_type: str, params: Dict[str, Any]) -> str:
    """计算动作的唯一 hash"""
    key = json.dumps({"action_type": action_type, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def is_cacheable(action_type: str) -> bool:
    """判断该动作类型是否允许缓存"""
    return action_type not in _NON_CACHEABLE_ACTIONS


def get_cached_result(action_type: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    查询缓存。返回缓存的结果 dict，或 None。
    """
    import app_state
    if not getattr(app_state, "ENABLE_IDEMPOTENT_TASKS", False):
        return None
    if not is_cacheable(action_type):
        return None

    cache_hash = _compute_hash(action_type, params)
    path = CACHE_DIR / f"{cache_hash}.json"
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ttl = getattr(app_state, "IDEMPOTENT_CACHE_TTL", 86400)
        if time.time() - data.get("created_at", 0) > ttl:
            path.unlink(missing_ok=True)
            return None
        return data.get("result")
    except Exception as e:
        logger.debug("Idempotent cache read failed: %s", e)
        return None


def store_cached_result(
    action_type: str,
    params: Dict[str, Any],
    result: Dict[str, Any],
) -> bool:
    """
    存储执行结果到缓存。仅缓存成功结果。
    返回是否存储成功。
    """
    import app_state
    if not getattr(app_state, "ENABLE_IDEMPOTENT_TASKS", False):
        return False
    if not is_cacheable(action_type):
        return False
    if not result.get("success", False):
        return False

    _ensure_dir()
    cache_hash = _compute_hash(action_type, params)
    entry = {
        "hash": cache_hash,
        "action_type": action_type,
        "created_at": time.time(),
        "result": result,
    }
    path = CACHE_DIR / f"{cache_hash}.json"
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
        return True
    except Exception as e:
        logger.debug("Idempotent cache write failed: %s", e)
        return False


def clear_cache() -> int:
    """清除全部幂等缓存，返回删除数量。"""
    _ensure_dir()
    count = 0
    for p in CACHE_DIR.glob("*.json"):
        try:
            p.unlink()
            count += 1
        except Exception:
            continue
    return count


def get_cache_stats() -> Dict[str, Any]:
    """返回缓存统计"""
    _ensure_dir()
    total = 0
    total_size = 0
    expired = 0
    import app_state
    ttl = getattr(app_state, "IDEMPOTENT_CACHE_TTL", 86400)
    now = time.time()

    for p in CACHE_DIR.glob("*.json"):
        total += 1
        total_size += p.stat().st_size
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if now - data.get("created_at", 0) > ttl:
                expired += 1
        except Exception:
            continue
    return {
        "total_entries": total,
        "expired_entries": expired,
        "total_size_bytes": total_size,
        "ttl_seconds": ttl,
    }
