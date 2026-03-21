"""
Duck Message Relay — Duck 间消息中转

支持 Duck ↔ Duck 直接通信（经主 Agent 中转）。
用于协作任务中的中间数据传递。
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from services.duck_protocol import DuckMessage, DuckMessageType

logger = logging.getLogger(__name__)


class DuckMessageRelay:
    """Duck 间消息中转服务（单例）"""

    _instance: Optional["DuckMessageRelay"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._message_log: List[Dict[str, Any]] = []
        self._max_log_size = 1000

    @classmethod
    def get_instance(cls) -> "DuckMessageRelay":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def relay_message(
        self,
        from_duck_id: str,
        to_duck_id: str,
        content: Any,
        msg_type: str = "relay",
    ) -> bool:
        """
        从一个 Duck 向另一个 Duck 转发消息。
        主 Agent 作为中间人进行中转。
        """
        msg = DuckMessage(
            type=DuckMessageType.CHAT,
            duck_id=from_duck_id,
            payload={
                "relay": True,
                "from_duck_id": from_duck_id,
                "to_duck_id": to_duck_id,
                "msg_type": msg_type,
                "content": content,
            },
        )

        # 尝试发送到目标 Duck
        ok = await self._send(to_duck_id, msg)

        # 记录日志
        self._log_message(from_duck_id, to_duck_id, msg_type, content, ok)

        if ok:
            logger.info(f"Relayed message: {from_duck_id} → {to_duck_id} ({msg_type})")
        else:
            logger.warning(f"Relay failed: {from_duck_id} → {to_duck_id} (target offline)")

        return ok

    async def broadcast_to_ducks(
        self,
        from_duck_id: str,
        content: Any,
        msg_type: str = "broadcast",
        exclude: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """向所有在线 Duck 广播消息"""
        from services.duck_registry import DuckRegistry

        registry = DuckRegistry.get_instance()
        await registry.initialize()
        online_ducks = await registry.list_online()

        exclude_set = set(exclude or [])
        exclude_set.add(from_duck_id)  # 不发给自己

        results = {}
        for duck in online_ducks:
            if duck.duck_id in exclude_set:
                continue
            ok = await self.relay_message(from_duck_id, duck.duck_id, content, msg_type)
            results[duck.duck_id] = ok

        return results

    async def _send(self, duck_id: str, msg: DuckMessage) -> bool:
        """向目标 Duck 发送消息（自动识别本地/远程）"""
        from services.duck_registry import DuckRegistry

        registry = DuckRegistry.get_instance()
        duck_info = await registry.get(duck_id)

        if not duck_info:
            return False

        if duck_info.is_local:
            # 本地 Duck 目前不支持接收中转消息（无消息处理循环）
            # 记录到日志，后续可扩展
            logger.debug(f"Relay to local duck {duck_id}: logged but not delivered")
            return True
        else:
            from routes.duck_ws import send_to_duck
            return await send_to_duck(duck_id, msg)

    def _log_message(
        self,
        from_id: str,
        to_id: str,
        msg_type: str,
        content: Any,
        success: bool,
    ):
        """记录中转消息日志"""
        self._message_log.append({
            "id": uuid.uuid4().hex[:8],
            "from": from_id,
            "to": to_id,
            "type": msg_type,
            "content_preview": str(content)[:200] if content else "",
            "success": success,
            "timestamp": time.time(),
        })
        # 限制日志大小
        if len(self._message_log) > self._max_log_size:
            self._message_log = self._message_log[-self._max_log_size:]

    def get_message_log(
        self,
        duck_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查询消息日志"""
        logs = self._message_log
        if duck_id:
            logs = [m for m in logs if m["from"] == duck_id or m["to"] == duck_id]
        return logs[-limit:]


def get_message_relay() -> DuckMessageRelay:
    return DuckMessageRelay.get_instance()
