"""
System Message Service - 系统消息管理
提供系统主动通知能力：存储、查询、推送系统消息给前端。

分类 category（对应前端 Tab）：
- system_error: 系统错误（如启动日志分析、工具加载失败）
- evolution:    进化/升级状态（自升级完成/失败、重启）
- task:        任务完成（自主任务结束）
- info:        其他

其他模块推送示例：
  from agent.system_message_service import get_system_message_service, MessageCategory
  get_system_message_service().add_info("标题", "内容", source="xxx", category=MessageCategory.EVOLUTION.value)
"""

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

from paths import DATA_DIR
MESSAGES_FILE = os.path.join(DATA_DIR, "system_messages.json")
MAX_MESSAGES = 200
# 同一条警告/错误在此时长内只保留一条（秒）
DEDUPE_WINDOW_SECONDS = 3600


class MessageLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class MessageCategory(str, Enum):
    """通知分类，对应前端 Tab 栏"""
    SYSTEM_ERROR = "system_error"   # 系统错误
    EVOLUTION = "evolution"         # 进化/升级状态
    TASK = "task"                   # 任务完成
    INFO = "info"                   # 其他


@dataclass
class SystemMessage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    level: str = MessageLevel.INFO.value
    title: str = ""
    content: str = ""
    source: str = ""
    category: str = MessageCategory.INFO.value
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    read: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SystemMessage":
        allowed = set(cls.__dataclass_fields__)
        kwargs = {k: v for k, v in d.items() if k in allowed}
        kwargs.setdefault("category", MessageCategory.INFO.value)
        return cls(**kwargs)


class SystemMessageService:
    """系统消息服务：存储 + 推送"""

    def __init__(self):
        self._messages: List[SystemMessage] = []
        self._broadcast_fn: Optional[Callable[[dict], Coroutine]] = None
        self._load()

    def set_broadcast(self, fn: Callable[[dict], Coroutine]) -> None:
        self._broadcast_fn = fn

    def add(
        self,
        level: str,
        title: str,
        content: str,
        source: str = "system",
        category: str = MessageCategory.INFO.value,
    ) -> Optional[SystemMessage]:
        if self._is_duplicate(title, category):
            logger.debug("System message deduplicated: title=%r category=%r", title, category)
            return None
        msg = SystemMessage(
            level=level, title=title, content=content, source=source, category=category
        )
        self._messages.append(msg)
        if len(self._messages) > MAX_MESSAGES:
            self._messages = self._messages[-MAX_MESSAGES:]
        self._save()
        self._push(msg)
        return msg

    def _is_duplicate(self, title: str, category: str) -> bool:
        """同一标题+分类在时间窗口内已存在则视为重复，只保留一条"""
        try:
            cutoff = datetime.now() - timedelta(seconds=DEDUPE_WINDOW_SECONDS)
            for m in self._messages:
                if m.title != title or m.category != category:
                    continue
                try:
                    # 时间戳为本地 ISO 格式，去掉时区后缀后解析
                    ts_str = m.timestamp.replace("Z", "").split("+")[0].strip()
                    ts = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    ts = datetime.now()
                if ts >= cutoff:
                    return True
            return False
        except Exception as e:
            logger.warning("Dedupe check failed: %s", e)
            return False

    def add_info(
        self, title: str, content: str, source: str = "system", category: str = MessageCategory.INFO.value
    ) -> SystemMessage:
        return self.add(MessageLevel.INFO.value, title, content, source, category)

    def add_warning(
        self, title: str, content: str, source: str = "system", category: str = MessageCategory.INFO.value
    ) -> SystemMessage:
        return self.add(MessageLevel.WARNING.value, title, content, source, category)

    def add_error(
        self, title: str, content: str, source: str = "system", category: str = MessageCategory.INFO.value
    ) -> SystemMessage:
        return self.add(MessageLevel.ERROR.value, title, content, source, category)

    def get_all(
        self, limit: int = 50, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        msgs = self._messages
        if category:
            msgs = [m for m in msgs if m.category == category]
        msgs = sorted(msgs, key=lambda m: m.timestamp, reverse=True)[:limit]
        return [m.to_dict() for m in msgs]

    def get_unread_count(self) -> int:
        return sum(1 for m in self._messages if not m.read)

    def mark_read(self, message_id: str) -> bool:
        for m in self._messages:
            if m.id == message_id:
                m.read = True
                self._save()
                return True
        return False

    def mark_all_read(self) -> int:
        count = 0
        for m in self._messages:
            if not m.read:
                m.read = True
                count += 1
        if count > 0:
            self._save()
        return count

    def clear(self) -> int:
        count = len(self._messages)
        self._messages.clear()
        self._save()
        return count

    def _push(self, msg: SystemMessage) -> None:
        if self._broadcast_fn:
            import asyncio
            payload = {
                "type": "system_notification",
                "notification": msg.to_dict(),
                "unread_count": self.get_unread_count(),
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast_fn(payload))
            except RuntimeError:
                try:
                    from .event_bus import get_event_bus
                    bus = get_event_bus()
                    bus.schedule(self._broadcast_fn(payload))
                except Exception as e:
                    logger.warning(f"SystemMessageService push failed: {e}")

    def _load(self) -> None:
        if not os.path.exists(MESSAGES_FILE):
            return
        try:
            with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._messages = [SystemMessage.from_dict(d) for d in data]
        except Exception as e:
            logger.warning(f"Failed to load system messages: {e}")
            self._messages = []

    def _save(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
                json.dump([m.to_dict() for m in self._messages], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save system messages: {e}")


_service: Optional[SystemMessageService] = None


def get_system_message_service() -> SystemMessageService:
    global _service
    if _service is None:
        _service = SystemMessageService()
    return _service
