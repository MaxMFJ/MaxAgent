"""
Event Bus - 发布订阅机制
用于解耦 AgentCore 与自愈、升级、错误收集等副作用逻辑
"""

import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger(__name__)

# 事件类型常量
EVENT_TOOL_FAILED = "tool_failed"
EVENT_PARSE_FAILED = "parse_failed"
EVENT_TOOL_NOT_FOUND = "tool_not_found"
EVENT_TRIGGER_UPGRADE = "trigger_upgrade"


class EventBus:
    """简单的同步发布订阅总线"""

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        """订阅事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Any], None]) -> None:
        """取消订阅"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def publish(self, event_type: str, payload: Any) -> None:
        """发布事件，同步调用所有订阅者"""
        if event_type not in self._handlers:
            return
        for handler in self._handlers[event_type][:]:  # 复制列表避免迭代时修改
            try:
                handler(payload)
            except Exception as e:
                logger.error(f"Event handler error for {event_type}: {e}", exc_info=True)


_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """重置（仅用于测试）"""
    global _event_bus
    _event_bus = None
