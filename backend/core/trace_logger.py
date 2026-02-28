"""
轻量 trace：按 task 记录 LLM/工具调用 span，写入 data/traces/{task_id}.jsonl。
便于排查「哪一步开始不稳定」、后续做 benchmark 与 ablation。
"""
import json
import logging
import os
import time

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
        path = os.path.join(TRACES_DIR, f"{task_id}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Trace append failed: %s", e)
