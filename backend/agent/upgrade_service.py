"""
Upgrade Service - 升级信号服务
监听 tool_not_found / trigger_upgrade，触发升级流程
只发出升级信号，不直接改核心流程
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from .event_bus import (
    get_event_bus,
    EVENT_TOOL_NOT_FOUND,
    EVENT_TRIGGER_UPGRADE,
)

logger = logging.getLogger(__name__)


class UpgradeService:
    """
    升级服务：订阅 tool_not_found / trigger_upgrade
    当收到事件时：1) on_broadcast 通知前端 2) on_trigger_upgrade 执行升级
    """

    def __init__(
        self,
        on_trigger_upgrade: Optional[
            Callable[[str, str, str], Coroutine[Any, Any, None]]
        ] = None,
        on_broadcast: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
        auto_upgrade: bool = True,
    ):
        self._on_trigger = on_trigger_upgrade
        self._on_broadcast = on_broadcast
        self._auto_upgrade = auto_upgrade

    def _emit_tool_upgrade_needed(
        self, session_id: str, reason: str, user_message: str, tool_name: str = ""
    ) -> None:
        chunk = {
            "type": "tool_upgrade_needed",
            "reason": reason,
            "tool_name": tool_name,
            "user_message": user_message,
        }
        if self._on_broadcast:
            try:
                result = self._on_broadcast(session_id, chunk)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.error(f"UpgradeService broadcast failed: {e}")

    def _on_tool_not_found(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        reason = payload.get("reason", "") or payload.get("error", "未知工具")
        user_message = payload.get("user_message", "")
        session_id = payload.get("session_id", "default")
        tool_name = payload.get("tool_name", "")
        self._emit_tool_upgrade_needed(session_id, reason, user_message, tool_name)
        if self._auto_upgrade and self._on_trigger:
            asyncio.create_task(self._on_trigger(reason, user_message, session_id))

    def _on_trigger_upgrade_event(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        reason = payload.get("reason", "") or payload.get("message", "需要升级")
        user_message = payload.get("user_message", "")
        session_id = payload.get("session_id", "default")
        tool_name = payload.get("tool_name", "")
        self._emit_tool_upgrade_needed(session_id, reason, user_message, tool_name)
        if self._auto_upgrade and self._on_trigger:
            asyncio.create_task(self._on_trigger(reason, user_message, session_id))

    def register(self) -> None:
        bus = get_event_bus()
        bus.subscribe(EVENT_TOOL_NOT_FOUND, self._on_tool_not_found)
        bus.subscribe(EVENT_TRIGGER_UPGRADE, self._on_trigger_upgrade_event)
        logger.info("UpgradeService registered to EventBus")

    def unregister(self) -> None:
        bus = get_event_bus()
        bus.unsubscribe(EVENT_TOOL_NOT_FOUND, self._on_tool_not_found)
        bus.unsubscribe(EVENT_TRIGGER_UPGRADE, self._on_trigger_upgrade_event)

    def set_on_trigger(self, fn: Callable[[str, str, str], Coroutine[Any, Any, None]]) -> None:
        self._on_trigger = fn

    def set_on_broadcast(self, fn: Callable[[str, Dict[str, Any]], Any]) -> None:
        self._on_broadcast = fn


_service: Optional[UpgradeService] = None


def get_upgrade_service(
    on_trigger_upgrade: Optional[Callable[[str, str, str], Coroutine[Any, Any, None]]] = None,
    on_broadcast: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    auto_upgrade: bool = True,
) -> UpgradeService:
    global _service
    if _service is None:
        _service = UpgradeService(
            on_trigger_upgrade=on_trigger_upgrade,
            on_broadcast=on_broadcast,
            auto_upgrade=auto_upgrade,
        )
        _service.register()
    else:
        if on_trigger_upgrade is not None:
            _service.set_on_trigger(on_trigger_upgrade)
        if on_broadcast is not None:
            _service.set_on_broadcast(on_broadcast)
    return _service
