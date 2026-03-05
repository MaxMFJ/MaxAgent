"""
轻量 trace：按 task 记录 LLM/工具调用 span，写入 data/traces/{task_id}.jsonl。
便于排查「哪一步开始不稳定」、后续做 benchmark 与 ablation。

v3.2 增强：
  - append_span: 自动补全 ts 字段
  - get_trace_summary: 读取 trace 文件，汇总 token 统计、步骤数、延迟分布
  - list_traces: 列出已记录的 task_id 列表（含文件大小和最后修改时间）
  - get_trace_spans: 返回指定 task 的所有 span（分页）
  - delete_trace: 删除指定 task 的 trace 文件
"""
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from paths import DATA_DIR
except ImportError:
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

TRACES_DIR = os.path.join(DATA_DIR, "traces")


def _ensure_traces_dir() -> None:
    try:
        os.makedirs(TRACES_DIR, exist_ok=True)
    except OSError as e:
        logger.debug("Trace dir not created: %s", e)


def append_span(task_id: str, span: dict) -> None:
    """追加一条 span 到 data/traces/{task_id}.jsonl。失败仅打日志，不抛错。"""
    try:
        _ensure_traces_dir()
        # 自动补全时间戳
        if "ts" not in span:
            span = dict(span)
            span["ts"] = time.time()
        path = os.path.join(TRACES_DIR, f"{task_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Trace append failed: %s", e)


def get_trace_spans(
    task_id: str,
    offset: int = 0,
    limit: int = 200,
    span_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    读取 task 的 trace spans，支持分页与类型过滤。
    span_type: None=全部, 'llm'=仅 LLM 调用, 'tool'=仅工具调用, 'step'=执行步骤等。
    """
    path = os.path.join(TRACES_DIR, f"{task_id}.jsonl")
    if not os.path.exists(path):
        return []
    spans: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    span = json.loads(line)
                    if span_type and span.get("type") != span_type:
                        continue
                    spans.append(span)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug("Trace read failed: %s", e)
        return []
    return spans[offset: offset + limit]


def get_trace_summary(task_id: str) -> Dict[str, Any]:
    """
    汇总指定 task 的 trace 统计信息：
    - span 总数、各类型数量
    - token 统计（prompt / completion / total）
    - 各步骤延迟分布（min / max / avg / p90 ms）
    - 工具调用成功 / 失败次数
    - 时间轴（first/last span 时间）
    """
    path = os.path.join(TRACES_DIR, f"{task_id}.jsonl")
    if not os.path.exists(path):
        return {"task_id": task_id, "exists": False}

    total_spans = 0
    type_counts: Dict[str, int] = {}
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    latencies: List[float] = []
    tool_success = 0
    tool_failure = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None
    errors: List[str] = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    span = json.loads(line)
                except json.JSONDecodeError:
                    continue

                total_spans += 1
                stype = span.get("type", "unknown")
                type_counts[stype] = type_counts.get(stype, 0) + 1

                ts = span.get("ts")
                if isinstance(ts, (int, float)):
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                # Token 统计
                usage = span.get("usage") or {}
                prompt_tokens += usage.get("prompt_tokens", 0) or span.get("prompt_tokens", 0)
                completion_tokens += usage.get("completion_tokens", 0) or span.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0) or span.get("total_tokens", 0)

                # 延迟统计
                lat = span.get("latency_ms") or span.get("duration_ms")
                if isinstance(lat, (int, float)) and lat >= 0:
                    latencies.append(float(lat))

                # 工具成功/失败
                if stype == "tool":
                    if span.get("success") is False or span.get("error"):
                        tool_failure += 1
                        err = span.get("error")
                        if err and len(errors) < 10:
                            errors.append(str(err)[:120])
                    else:
                        tool_success += 1

    except Exception as e:
        logger.debug("Trace summary failed: %s", e)
        return {"task_id": task_id, "exists": True, "error": str(e)}

    # 计算 total_tokens（若未从 usage 获取）
    if total_tokens == 0 and (prompt_tokens + completion_tokens) > 0:
        total_tokens = prompt_tokens + completion_tokens

    # 延迟分布
    latency_stats: Dict[str, Any] = {}
    if latencies:
        latencies.sort()
        n = len(latencies)
        p90_idx = min(int(n * 0.9), n - 1)
        latency_stats = {
            "count": n,
            "min_ms": round(latencies[0], 1),
            "max_ms": round(latencies[-1], 1),
            "avg_ms": round(sum(latencies) / n, 1),
            "p90_ms": round(latencies[p90_idx], 1),
        }

    duration_s: Optional[float] = None
    if first_ts and last_ts:
        duration_s = round(last_ts - first_ts, 2)

    return {
        "task_id": task_id,
        "exists": True,
        "total_spans": total_spans,
        "type_counts": type_counts,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
        },
        "latency": latency_stats,
        "tool_calls": {
            "success": tool_success,
            "failure": tool_failure,
        },
        "timeline": {
            "first_ts": first_ts,
            "last_ts": last_ts,
            "duration_s": duration_s,
        },
        "recent_errors": errors,
    }


def list_traces(limit: int = 50) -> List[Dict[str, Any]]:
    """
    列出已记录的 trace 文件（按最后修改时间倒序）。
    返回 [{"task_id": ..., "size_bytes": ..., "mtime": ..., "span_count": ...}, ...]
    """
    _ensure_traces_dir()
    results: List[Dict[str, Any]] = []
    try:
        for fname in os.listdir(TRACES_DIR):
            if not fname.endswith(".jsonl"):
                continue
            task_id = fname[:-6]  # strip .jsonl
            fpath = os.path.join(TRACES_DIR, fname)
            try:
                stat = os.stat(fpath)
                # 计算行数（= span 数量）
                span_count = 0
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            span_count += 1
                results.append({
                    "task_id": task_id,
                    "size_bytes": stat.st_size,
                    "mtime": stat.st_mtime,
                    "span_count": span_count,
                })
            except Exception:
                continue
    except Exception as e:
        logger.debug("List traces failed: %s", e)
    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:limit]


def delete_trace(task_id: str) -> bool:
    """删除指定 task 的 trace 文件。成功返回 True。"""
    path = os.path.join(TRACES_DIR, f"{task_id}.jsonl")
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    except Exception as e:
        logger.debug("Delete trace failed: %s", e)
        return False
