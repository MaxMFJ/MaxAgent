"""
WebSocket 连接管理器
管理多客户端连接、会话广播、安全发送。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from app_state import get_server_status, set_server_status, ServerStatus

logger = logging.getLogger(__name__)


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
                del self._connections[client_id]
                if session_id in self._session_connections:
                    self._session_connections[session_id].discard(client_id)
                    if not self._session_connections[session_id]:
                        del self._session_connections[session_id]
                logger.info(f"Client disconnected: {client_id}")

    async def broadcast_to_session(self, session_id: str, message: dict, exclude_client: str = None):
        if session_id not in self._session_connections:
            return
        client_ids = list(self._session_connections[session_id])
        disconnected = []
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            if client_id in self._connections:
                conn = self._connections[client_id]
                try:
                    await conn.websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to {client_id}: {e}")
                    disconnected.append(client_id)
        for client_id in disconnected:
            await self.disconnect(client_id)

    async def broadcast_all(self, message: dict, exclude_client: str = None):
        client_ids = list(self._connections.keys())
        disconnected = []
        for client_id in client_ids:
            if client_id == exclude_client:
                continue
            if client_id in self._connections:
                conn = self._connections[client_id]
                try:
                    await conn.websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to {client_id}: {e}")
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


async def safe_send_json(websocket: WebSocket, message: dict) -> bool:
    """
    安全发送 JSON，客户端已断开时捕获异常。
    返回 True 表示发送成功，False 表示连接已断开。
    """
    try:
        await websocket.send_json(message)
        return True
    except WebSocketDisconnect:
        logger.debug("Client disconnected during send")
        return False
    except Exception as e:
        err_msg = str(e).lower()
        if "not connected" in err_msg or "accept" in err_msg or "1006" in err_msg:
            logger.debug(f"WebSocket closed, skip send: {e}")
            return False
        raise
