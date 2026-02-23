"""
Error Service - 错误收集服务
监听 tool_failed / parse_failed，写入错误队列
不阻塞主线程，不侵入 AgentCore
"""

import json
import logging
import os
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from .event_bus import get_event_bus, EVENT_TOOL_FAILED, EVENT_PARSE_FAILED
from .event_schema import Event

logger = logging.getLogger(__name__)

MAX_QUEUE_SIZE = 100


class ErrorService:
    """错误收集服务，订阅 EventBus 并记录错误"""

    def __init__(self, persist_path: Optional[str] = None):
        self._queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._persist_path = persist_path
        self._enabled = True

    def _on_tool_failed(self, event: Event) -> None:
        if not self._enabled:
            return
        payload = event.payload if isinstance(event.payload, dict) else {"raw": str(event.payload)}
        self._append({"event": EVENT_TOOL_FAILED, "timestamp": datetime.now().isoformat(), "payload": payload})

    def _on_parse_failed(self, event: Event) -> None:
        if not self._enabled:
            return
        payload = event.payload if isinstance(event.payload, dict) else {"raw": str(event.payload)}
        self._append({"event": EVENT_PARSE_FAILED, "timestamp": datetime.now().isoformat(), "payload": payload})

    def _append(self, entry: Dict[str, Any]) -> None:
        self._queue.append(entry)
        logger.info(f"ErrorService: recorded {entry['event']}")
        if self._persist_path:
            self._persist_async(entry)

    def _persist_async(self, entry: Dict[str, Any]) -> None:
        try:
            path = self._persist_path
            existing: List[Dict] = []
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, IOError):
                    existing = []
            existing.append(entry)
            if len(existing) > MAX_QUEUE_SIZE:
                existing = existing[-MAX_QUEUE_SIZE:]
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=0)
        except Exception as e:
            logger.warning(f"ErrorService persist failed: {e}")

    def register(self) -> None:
        bus = get_event_bus()
        bus.subscribe(EVENT_TOOL_FAILED, self._on_tool_failed)
        bus.subscribe(EVENT_PARSE_FAILED, self._on_parse_failed)
        logger.info("ErrorService registered to EventBus")

    def unregister(self) -> None:
        bus = get_event_bus()
        bus.unsubscribe(EVENT_TOOL_FAILED, self._on_tool_failed)
        bus.unsubscribe(EVENT_PARSE_FAILED, self._on_parse_failed)

    def pop_all(self) -> List[Dict[str, Any]]:
        items = list(self._queue)
        self._queue.clear()
        return items

    def get_queue_size(self) -> int:
        return len(self._queue)


_error_service: Optional[ErrorService] = None


def get_error_service(persist_path: Optional[str] = None) -> ErrorService:
    global _error_service
    if _error_service is None:
        _error_service = ErrorService(persist_path=persist_path)
        _error_service.register()
    return _error_service
