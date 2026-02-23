"""
Self-Healing Worker - 自愈后台 worker
监听 parse_failed，在会话上下文中触发自愈并广播进度
不允许从 AgentCore 内部直接调用
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from .event_bus import get_event_bus, EVENT_PARSE_FAILED

logger = logging.getLogger(__name__)


class SelfHealingWorker:
    """
    自愈 Worker：订阅 parse_failed，执行自愈并推送进度
    on_broadcast: (session_id, chunk) -> None 用于推送到 WebSocket
    """

    def __init__(
        self,
        on_broadcast: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    ):
        self._on_broadcast = on_broadcast
        self._healing_in_progress: Dict[str, bool] = {}  # session_id -> bool
        self._enabled = True

    def _on_parse_failed(self, payload: Any) -> None:
        if not self._enabled:
            return
        if not isinstance(payload, dict):
            return
        session_id = payload.get("session_id", "default")
        if self._healing_in_progress.get(session_id):
            logger.info("SelfHealing: already healing for session, skip")
            return

        # 异步执行自愈，不阻塞 EventBus
        asyncio.create_task(self._run_heal(session_id, payload))

    async def _run_heal(self, session_id: str, payload: Dict[str, Any]) -> None:
        self._healing_in_progress[session_id] = True
        try:
            try:
                from .self_healing import get_self_healing_agent
            except ImportError:
                logger.warning("Self-healing module not available")
                self._broadcast(session_id, {
                    "type": "self_healing_status",
                    "status": "unavailable",
                    "message": "自愈模块不可用",
                })
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

            async for update in healer.heal(
                error_message=error_message,
                stack_trace=payload.get("stack_trace", ""),
                context=context,
            ):
                self._broadcast(session_id, {
                    "type": "self_healing_update",
                    **update,
                })
        except Exception as e:
            logger.error(f"Self-healing failed: {e}", exc_info=True)
            self._broadcast(session_id, {
                "type": "self_healing_error",
                "error": str(e),
            })
        finally:
            self._healing_in_progress.pop(session_id, None)

    def _broadcast(self, session_id: str, chunk: Dict[str, Any]) -> None:
        if self._on_broadcast:
            try:
                result = self._on_broadcast(session_id, chunk)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
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
) -> SelfHealingWorker:
    global _worker
    if _worker is None:
        _worker = SelfHealingWorker(on_broadcast=on_broadcast)
        _worker.register()
    elif on_broadcast is not None:
        _worker.set_on_broadcast(on_broadcast)
    return _worker
