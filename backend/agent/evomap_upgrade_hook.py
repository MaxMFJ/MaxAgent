"""
EvoMap Upgrade Hook
Intercepts tool_not_found events and queries EvoMap network for solutions
before falling back to self-upgrade.
"""

import logging
from typing import Optional

from .event_bus import get_event_bus, EVENT_TOOL_NOT_FOUND
from .event_schema import Event

logger = logging.getLogger(__name__)


class EvoMapUpgradeHook:
    """
    Subscribes to tool_not_found events.
    Before self-upgrade triggers, checks if EvoMap network has a matching
    capsule/gene that can resolve the capability gap.
    """

    def __init__(self):
        bus = get_event_bus()
        bus.subscribe(EVENT_TOOL_NOT_FOUND, self._on_tool_not_found)
        logger.info("EvoMapUpgradeHook registered on EventBus")

    def _on_tool_not_found(self, event: Event) -> None:
        """Query EvoMap for the missing capability (non-blocking)."""
        payload = event.payload
        if not isinstance(payload, dict):
            return

        tool_name = payload.get("tool_name", "")
        user_message = payload.get("user_message", "")
        session_id = payload.get("session_id", "default")

        if not tool_name:
            return

        bus = get_event_bus()
        bus.schedule(self._async_check_evomap(tool_name, user_message, session_id))

    async def _async_check_evomap(self, tool_name: str, user_message: str, session_id: str):
        """First check local Capsule registry; then EvoMap network for the missing tool."""
        # 1) 本地 Capsule 库：若有匹配的可执行 Capsule，仅记录日志，由 Agent 通过 capsule 工具执行
        try:
            from .capsule_registry import get_capsule_registry
            registry = get_capsule_registry()
            local_caps = registry.find_capsule_by_task(user_message or tool_name)
            if local_caps:
                logger.info(
                    f"Local Capsule(s) found for missing tool '{tool_name}': {[c.id for c in local_caps[:3]]}. "
                    "Agent can use capsule(action=execute, capsule_id=..., inputs=...) to run."
                )
                return
        except Exception as e:
            logger.debug(f"Local capsule lookup failed: {e}")

        # 2) EvoMap 进化网络
        try:
            from .evomap_service import get_evomap_service
            service = get_evomap_service()
            if not service._initialized:
                return

            signals = [tool_name, "capability_gap", "tool_not_found"]
            result = await service.resolve_capability(user_message, signals)

            if result.get("found"):
                capsules = result.get("capsules", [])
                logger.info(
                    f"EvoMap found {len(capsules)} capsules for missing tool '{tool_name}'. "
                    "Strategies available from evolution network."
                )
                for cap_data in capsules[:1]:
                    await service.client.inherit_capsule(cap_data)
            else:
                logger.debug(f"EvoMap has no capsules for tool '{tool_name}'")

        except Exception as e:
            logger.debug(f"EvoMap upgrade hook check failed: {e}")


_hook: Optional[EvoMapUpgradeHook] = None


def init_evomap_upgrade_hook() -> EvoMapUpgradeHook:
    global _hook
    if _hook is None:
        _hook = EvoMapUpgradeHook()
    return _hook
