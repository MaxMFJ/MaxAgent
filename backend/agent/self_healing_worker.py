"""
Self-Healing Worker - 自愈后台 worker
监听 parse_failed，熔断保护，在会话上下文中触发自愈并广播进度
不允许从 AgentCore 内部直接调用
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from .event_bus import get_event_bus, EVENT_PARSE_FAILED
from .event_schema import Event

logger = logging.getLogger(__name__)


class SelfHealingWorker:
    """
    自愈 Worker：订阅 parse_failed
    熔断机制：error_count >= threshold 时跳过，cooldown 后重置
    on_broadcast: (session_id, chunk) -> 用于推送到 WebSocket
    """

    def __init__(
        self,
        on_broadcast: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        threshold: int = 3,
        cooldown: float = 60.0,
    ):
        self._on_broadcast = on_broadcast
        self._healing_in_progress: Dict[str, bool] = {}
        self._enabled = True
        self._error_count = 0
        self._last_reset = time.time()
        self._threshold = threshold
        self._cooldown = cooldown

    def _on_parse_failed(self, event: Event) -> None:
        if not self._enabled:
            return
        payload = event.payload
        if not isinstance(payload, dict):
            return

        now = time.time()
        if now - self._last_reset > self._cooldown:
            self._error_count = 0
            self._last_reset = now

        if self._error_count >= self._threshold:
            logger.warning(
                "SelfHealing blocked by circuit breaker (count=%d, threshold=%d)",
                self._error_count,
                self._threshold,
            )
            return

        self._error_count += 1

        session_id = payload.get("session_id", "default")
        if self._healing_in_progress.get(session_id):
            logger.info("SelfHealing: already healing for session, skip")
            return

        bus = get_event_bus()
        bus.schedule(self._run_heal(session_id, payload))

    async def _run_heal(self, session_id: str, payload: Dict[str, Any]) -> None:
        self._healing_in_progress[session_id] = True
        try:
            try:
                from .self_healing import get_self_healing_agent
            except ImportError:
                logger.warning("Self-healing module not available")
                self._broadcast(session_id, {"type": "self_healing_status", "status": "unavailable", "message": "自愈模块不可用"})
                return

            healer = get_self_healing_agent()
            error_message = payload.get("error", "") or payload.get("message", "解析失败")
            context = payload.get("context", {})
            context["session_id"] = session_id
            context["auto_confirm"] = True

            self._broadcast(session_id, {
                "type": "self_healing_triggered",
                "reason": "tool_parse_failure",
                "message": "检测到工具调用解析失败，正在尝试自愈...",
            })

            async for update in healer.heal(error_message=error_message, stack_trace=payload.get("stack_trace", ""), context=context):
                self._broadcast(session_id, {"type": "self_healing_update", **update})
        except Exception as e:
            logger.error(f"Self-healing failed: {e}", exc_info=True)
            self._broadcast(session_id, {"type": "self_healing_error", "error": str(e)})
        finally:
            self._healing_in_progress.pop(session_id, None)

    def _broadcast(self, session_id: str, chunk: Dict[str, Any]) -> None:
        if self._on_broadcast:
            try:
                result = self._on_broadcast(session_id, chunk)
                bus = get_event_bus()
                if asyncio.iscoroutine(result):
                    bus.schedule(result)
            except Exception as e:
                logger.error(f"SelfHealingWorker broadcast failed: {e}")

    def register(self) -> None:
        bus = get_event_bus()
        bus.subscribe(EVENT_PARSE_FAILED, self._on_parse_failed)
        logger.info("SelfHealingWorker registered to EventBus")

    def unregister(self) -> None:
        bus = get_event_bus()
        bus.unsubscribe(EVENT_PARSE_FAILED, self._on_parse_failed)

    def set_on_broadcast(self, fn: Callable[[str, Dict[str, Any]], Any]) -> None:
        self._on_broadcast = fn


_worker: Optional[SelfHealingWorker] = None


def get_self_healing_worker(
    on_broadcast: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    threshold: int = 3,
    cooldown: float = 60.0,
) -> SelfHealingWorker:
    global _worker
    if _worker is None:
        _worker = SelfHealingWorker(on_broadcast=on_broadcast, threshold=threshold, cooldown=cooldown)
        _worker.register()
    elif on_broadcast is not None:
        _worker.set_on_broadcast(on_broadcast)
    return _worker
