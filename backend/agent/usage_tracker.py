"""
Usage Statistics Tracker
========================
Records every LLM API call to local JSONL storage for the monitoring dashboard.
Data is persisted per-day as ``data/usage_stats/calls_YYYY-MM-DD.jsonl``.

Singleton access via ``UsageTracker.shared()``.
"""

import json
import os
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "data", "usage_stats"))


class UsageTracker:
    """Thread-safe singleton that records LLM API calls to local JSONL storage."""

    _instance: Optional["UsageTracker"] = None
    _lock = threading.Lock()

    @classmethod
    def shared(cls) -> "UsageTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._file_lock = threading.Lock()
        self._cache: List[Dict[str, Any]] = []
        self._cache_loaded = False
        # Sliding windows for real-time RPM/TPM
        self._rpm_window: List[float] = []
        self._tpm_window: List[tuple] = []
        # Rate limits (configurable via env)
        self.rpm_limit: int = int(os.environ.get("MACAGENT_RPM_LIMIT", "60"))
        self.tpm_limit: int = int(os.environ.get("MACAGENT_TPM_LIMIT", "200000"))

    def check_rate_limit(self) -> Optional[str]:
        """Pre-call rate check. Returns error message if limit exceeded, None if OK."""
        now = time.time()
        cutoff = now - 60  # 1 分钟窗口
        rpm = sum(1 for t in self._rpm_window if t > cutoff)
        tpm = sum(tk for t, tk in self._tpm_window if t > cutoff)
        if rpm >= self.rpm_limit:
            return f"请求频率超限: {rpm}/{self.rpm_limit} RPM，请稍后重试"
        if tpm >= self.tpm_limit:
            return f"Token 用量超限: {tpm}/{self.tpm_limit} TPM，请稍后重试"
        return None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _get_log_file(self) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        return DATA_DIR / f"calls_{date_str}.jsonl"

    def record_call(
        self,
        model: str,
        provider: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        success: bool = True,
        latency_ms: int = 0,
        error: Optional[str] = None,
    ):
        """Record a single LLM API call."""
        now = time.time()
        record = {
            "ts": now,
            "dt": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "model": model or "unknown",
            "provider": provider or "unknown",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "success": success,
            "latency_ms": latency_ms,
            "error": error,
        }

        # Sliding windows (keep last 10 min)
        cutoff = now - 600
        self._rpm_window = [t for t in self._rpm_window if t > cutoff]
        self._tpm_window = [(t, tk) for t, tk in self._tpm_window if t > cutoff]
        self._rpm_window.append(now)
        self._tpm_window.append((now, total_tokens))

        # Persist
        with self._file_lock:
            try:
                fp = self._get_log_file()
                with open(fp, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"Failed to write usage record: {e}")

        # Cache
        self._cache.append(record)

    # ------------------------------------------------------------------
    # Reading helpers
    # ------------------------------------------------------------------

    def _load_all_records(self) -> List[Dict[str, Any]]:
        """Load all records across day-files. Cached after first read."""
        if self._cache_loaded:
            return self._cache
        records: List[Dict[str, Any]] = []
        try:
            for fp in sorted(DATA_DIR.glob("calls_*.jsonl")):
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.warning(f"Failed to load usage records: {e}")
        self._cache = records
        self._cache_loaded = True
        return records

    # ------------------------------------------------------------------
    # Public queries
    # ------------------------------------------------------------------

    def get_overview(self) -> Dict[str, Any]:
        """Top-card statistics + sparkline data."""
        records = self._load_all_records()
        now = time.time()

        total_requests = len(records)
        total_tokens = sum(r.get("total_tokens", 0) for r in records)
        total_prompt = sum(r.get("prompt_tokens", 0) for r in records)
        total_completion = sum(r.get("completion_tokens", 0) for r in records)
        success_count = sum(1 for r in records if r.get("success", True))

        # Avg RPM / TPM over last 10 minutes
        cutoff_10m = now - 600
        recent = [r for r in records if r.get("ts", 0) > cutoff_10m]
        minutes_span = min(10.0, max((now - min((r.get("ts", now) for r in recent), default=now)) / 60.0, 1.0)) if recent else 1.0
        rpm = len(recent) / minutes_span
        tpm = sum(r.get("total_tokens", 0) for r in recent) / minutes_span

        # Per-minute sparklines (last 30 min)
        rpm_history: List[float] = []
        tpm_history: List[float] = []
        for i in range(30):
            m_start = now - (30 - i) * 60
            m_end = m_start + 60
            bucket = [r for r in records if m_start <= r.get("ts", 0) < m_end]
            rpm_history.append(len(bucket))
            tpm_history.append(sum(r.get("total_tokens", 0) for r in bucket))

        return {
            "total_requests": total_requests,
            "success_count": success_count,
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "avg_rpm": round(rpm, 3),
            "avg_tpm": round(tpm, 3),
            "rpm_history": rpm_history,
            "tpm_history": tpm_history,
            "request_history": rpm_history,
        }

    def get_model_analysis(self) -> Dict[str, Any]:
        """Model-level breakdowns for charts."""
        records = self._load_all_records()
        now = time.time()

        model_tokens: Dict[str, int] = defaultdict(int)
        model_calls: Dict[str, int] = defaultdict(int)

        for r in records:
            m = r.get("model", "unknown")
            model_tokens[m] += r.get("total_tokens", 0)
            model_calls[m] += 1

        consumption_distribution = [
            {"model": m, "tokens": t}
            for m, t in sorted(model_tokens.items(), key=lambda x: x[1], reverse=True)
        ]

        call_distribution = [
            {"model": m, "count": c}
            for m, c in sorted(model_calls.items(), key=lambda x: x[1], reverse=True)
        ]

        call_ranking = call_distribution[:10]

        # Hourly trend (last 48h)
        trend: List[Dict[str, Any]] = []
        for i in range(48):
            h_start = now - (48 - i) * 3600
            h_end = h_start + 3600
            bucket = [r for r in records if h_start <= r.get("ts", 0) < h_end]
            tokens = sum(r.get("total_tokens", 0) for r in bucket)
            label = datetime.fromtimestamp(h_start).strftime("%m-%d %H:00")
            trend.append({"time": label, "tokens": tokens})

        return {
            "consumption_distribution": consumption_distribution,
            "consumption_trend": trend,
            "call_distribution": call_distribution,
            "call_ranking": call_ranking,
        }
