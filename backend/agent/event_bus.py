"""
Event Bus - 支持优先级的发布订阅
用于解耦 AgentCore 与自愈、升级、错误收集等副作用逻辑
使用 PriorityQueue + 后台 worker 按优先级调度
"""

import asyncio
import logging
import threading
import time
from queue import Empty, PriorityQueue
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from .event_schema import Event

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 事件类型常量
EVENT_TOOL_FAILED = "tool_failed"
EVENT_PARSE_FAILED = "parse_failed"
EVENT_TOOL_NOT_FOUND = "tool_not_found"
EVENT_TRIGGER_UPGRADE = "trigger_upgrade"


class EventBus:
    """
    支持优先级的 EventBus
    publish 只接受 Event 实例，按 priority 调度（越小越优先）
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable[[Event], None]]] = {}
        self._queue: PriorityQueue = PriorityQueue()
        self._running = True
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置主事件循环，用于 schedule 异步任务"""
        self._loop = loop

    def schedule(self, coro) -> None:
        """从 worker 线程调度协程到主事件循环"""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:
            logger.warning("EventBus: no running loop for schedule")

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """订阅事件"""
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """取消订阅"""
        with self._lock:
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                except ValueError:
                    pass

    def publish(self, event: Event) -> None:
        """发布事件，加入优先级队列（priority 越小越优先）"""
        if not isinstance(event, Event):
            raise TypeError("publish requires Event instance")
        # (priority, timestamp, event) 确保同优先级按时间排序
        self._queue.put((event.priority, event.timestamp, event))

    def _worker_loop(self) -> None:
        """后台 worker：按优先级消费队列"""
        while self._running:
            try:
                _, _, event = self._queue.get(timeout=0.1)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"EventBus worker get error: {e}")
                continue

            handlers = []
            with self._lock:
                handlers = list(self._handlers.get(event.type, []))

            for handler in handlers:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error for {event.type}: {e}", exc_info=True)

    def stop(self) -> None:
        """停止 worker（仅用于测试）"""
        self._running = False


_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """重置（仅用于测试）"""
    global _event_bus
    if _event_bus:
        _event_bus.stop()
    _event_bus = None
