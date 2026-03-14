"""
WebSocket 连接管理器
管理多客户端连接、会话广播、安全发送。
支持断线期间重要消息缓冲（duck_task_complete / duck_task_retry / done 等）。
"""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from app_state import get_server_status, set_server_status, ServerStatus

logger = logging.getLogger(__name__)

# 需要缓冲的重要消息类型（断线期间不能丢失）
_BUFFERED_MSG_TYPES = frozenset({
    "duck_task_complete", "duck_task_retry", "duck_task_progress",
    "done", "task_complete", "auto_delegated_to_duck",
})
# 每个 session 最多缓冲多少条
_MAX_BUFFER_PER_SESSION = 50
# 缓冲消息过期时间（秒）
_BUFFER_EXPIRE_SECS = 600


class ClientType(str, Enum):
    MAC = "mac"
    IOS = "ios"
    UNKNOWN = "unknown"


@dataclass
class ClientConnection:
    websocket: WebSocket
    client_id: str
    client_type: ClientType
    session_id: str
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)


class ConnectionManager:
    """管理所有 WebSocket 连接，支持多客户端同步"""

    def __init__(self):
        self._connections: Dict[str, ClientConnection] = {}
        self._session_connections: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        # 断线消息缓冲：session_id → deque[(timestamp, message)]
        self._pending_buffers: Dict[str, deque] = {}

    def get_server_status(self) -> ServerStatus:
        return get_server_status()

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        client_type: ClientType = ClientType.UNKNOWN,
        session_id: str = "default",
    ) -> ClientConnection:
        async with self._lock:
            conn = ClientConnection(
                websocket=websocket,
                client_id=client_id,
                client_type=client_type,
                session_id=session_id,
            )
            self._connections[client_id] = conn
            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(client_id)
            logger.info(f"Client connected: {client_id} ({client_type.value}), session: {session_id}")
            return conn

    async def disconnect(self, client_id: str):
        async with self._lock:
            if client_id in self._connections:
                conn = self._connections[client_id]
                session_id = conn.session_id
                # 清理 per-WebSocket 写锁
                remove_ws_write_lock(conn.websocket)
                del self._connections[client_id]
                if session_id in self._session_connections:
                    self._session_connections[session_id].discard(client_id)
                    if not self._session_connections[session_id]:
                        del self._session_connections[session_id]
                logger.info(f"Client disconnected: {client_id}")

    async def update_session(self, client_id: str, new_session_id: str) -> bool:
        """将指定客户端迁移到新 session，并更新 _session_connections 索引。
        Returns True if the session was actually changed."""
        async with self._lock:
            if client_id not in self._connections:
                return False
            old_session_id = self._connections[client_id].session_id
            if old_session_id == new_session_id:
                return False
            self._connections[client_id].session_id = new_session_id
            if old_session_id in self._session_connections:
                self._session_connections[old_session_id].discard(client_id)
                if not self._session_connections[old_session_id]:
                    del self._session_connections[old_session_id]
            if new_session_id not in self._session_connections:
                self._session_connections[new_session_id] = set()
            self._session_connections[new_session_id].add(client_id)
            logger.info(f"Client {client_id} session updated: {old_session_id} → {new_session_id}")
            return True

    async def broadcast_to_session(self, session_id: str, message: dict, exclude_client: str = None):
        # 检查 session 是否有在线客户端
        if session_id not in self._session_connections or not self._session_connections[session_id]:
            # 无在线客户端 — 缓冲重要消息
            msg_type = message.get("type", "")
            if msg_type in _BUFFERED_MSG_TYPES:
                self._buffer_message(session_id, message)
            return
        client_ids = list(self._session_connections[session_id])
        disconnected = []
        sent_count = 0
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            if client_id in self._connections:
                conn = self._connections[client_id]
                if not await safe_send_json(conn.websocket, message):
                    disconnected.append(client_id)
                else:
                    sent_count += 1
        for client_id in disconnected:
            await self.disconnect(client_id)

        # 如果所有发送都失败了，缓冲重要消息
        if sent_count == 0:
            msg_type = message.get("type", "")
            if msg_type in _BUFFERED_MSG_TYPES:
                self._buffer_message(session_id, message)
        
        # 检查 session 是否还有客户端，如果没有则触发孤儿任务处理
        if disconnected and self.get_session_client_count(session_id) == 0:
            try:
                # 延迟导入避免循环依赖
                from ws_handler import _handle_client_disconnect
                await _handle_client_disconnect(session_id)
                logger.info(f"Orphan task handling triggered for session {session_id} after broadcast failures")
            except Exception as e:
                logger.debug(f"Failed to trigger orphan handling: {e}")

    def _buffer_message(self, session_id: str, message: dict):
        """缓冲重要消息，供客户端重连后补发"""
        if session_id not in self._pending_buffers:
            self._pending_buffers[session_id] = deque(maxlen=_MAX_BUFFER_PER_SESSION)
        self._pending_buffers[session_id].append((time.time(), message))
        logger.debug(f"Buffered {message.get('type')} for session {session_id} "
                     f"(buffer size: {len(self._pending_buffers[session_id])})")

    async def flush_pending(self, session_id: str, websocket: WebSocket):
        """客户端重连后，补发缓冲的重要消息"""
        buf = self._pending_buffers.pop(session_id, None)
        if not buf:
            return
        now = time.time()
        flushed = 0
        for ts, msg in buf:
            if now - ts > _BUFFER_EXPIRE_SECS:
                continue  # 过期消息丢弃
            if await safe_send_json(websocket, msg):
                flushed += 1
        if flushed:
            logger.info(f"Flushed {flushed} pending messages to session {session_id}")

    async def broadcast_all(self, message: dict, exclude_client: str = None):
        client_ids = list(self._connections.keys())
        disconnected = []
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            if client_id in self._connections:
                conn = self._connections[client_id]
                if not await safe_send_json(conn.websocket, message):
                    disconnected.append(client_id)
        for client_id in disconnected:
            await self.disconnect(client_id)

    def get_connection(self, client_id: str) -> Optional[ClientConnection]:
        return self._connections.get(client_id)

    def get_session_clients(self, session_id: str) -> list:
        if session_id not in self._session_connections:
            return []
        return [
            {
                "client_id": cid,
                "client_type": self._connections[cid].client_type.value,
                "connected_at": self._connections[cid].connected_at.isoformat(),
            }
            for cid in self._session_connections[session_id]
            if cid in self._connections
        ]

    def get_session_client_count(self, session_id: str) -> int:
        """返回 session 内当前在线的客户端数量"""
        if session_id not in self._session_connections:
            return 0
        return len(self._session_connections[session_id])

    def get_stats(self) -> dict:
        type_counts: Dict[str, int] = {}
        for conn in self._connections.values():
            t = conn.client_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_connections": len(self._connections),
            "sessions": len(self._session_connections),
            "by_type": type_counts,
        }


# 全局单例
connection_manager = ConnectionManager()


# ============== 广播辅助函数 ==============

async def broadcast_status_change(status: str, message: str = ""):
    if status in [e.value for e in ServerStatus]:
        set_server_status(ServerStatus(status))
    msg = {
        "type": "status_change",
        "status": status,
        "message": message,
        "timestamp": datetime.now().isoformat(),
    }
    await connection_manager.broadcast_all(msg)


async def broadcast_upgrade_message(msg: dict):
    await connection_manager.broadcast_all(msg)


# ============== Per-WebSocket 写锁注册表 ==============
# 防止心跳任务、流式推送、广播等并发写入同一 WebSocket 导致帧损坏断线
_ws_write_locks: Dict[int, asyncio.Lock] = {}


def get_ws_write_lock(websocket: WebSocket) -> asyncio.Lock:
    """获取 WebSocket 实例的写锁（不存在则创建）"""
    ws_id = id(websocket)
    if ws_id not in _ws_write_locks:
        _ws_write_locks[ws_id] = asyncio.Lock()
    return _ws_write_locks[ws_id]


def remove_ws_write_lock(websocket: WebSocket):
    """清理 WebSocket 写锁（断开连接时调用）"""
    _ws_write_locks.pop(id(websocket), None)


async def safe_send_json(websocket: WebSocket, message: dict) -> bool:
    """
    安全发送 JSON，使用 per-WebSocket 写锁防止并发帧损坏。
    客户端已断开或服务端关闭时捕获异常。
    返回 True 表示发送成功，False 表示连接已断开/不可用。
    """
    lock = get_ws_write_lock(websocket)
    try:
        async with lock:
            await websocket.send_json(message)
        return True
    except WebSocketDisconnect:
        logger.debug("Client disconnected during send")
        return False
    except RuntimeError as e:
        # 服务端关闭/重载时 ASGI 已发送 websocket.close，再 send 会报此错
        err_msg = str(e).lower()
        if "websocket.close" in err_msg or "response already completed" in err_msg:
            logger.debug(f"WebSocket already closed (shutdown?), skip send: {e}")
            return False
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "not connected" in err_msg or "accept" in err_msg or "1006" in err_msg:
            logger.debug(f"WebSocket closed, skip send: {e}")
            return False
        raise
