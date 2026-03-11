"""
StreamChunkDispatcher — 统一的流式 chunk 分发器
==================================================
Chat 和 Autonomous 的 streaming 循环共享 90% 相同的逻辑：
  1. 从 generator 读取 chunk
  2. 写入 TaskTracker 缓冲
  3. 发送给当前客户端（WebSocket）
  4. 广播给 session 内其他客户端
  5. 广播监控事件
  6. 错误/停止/完成 时的清理

此模块提取这些共同逻辑，消除 ws_handler.py 中约 200 行重复代码。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class StreamChunkDispatcher:
    """
    统一的 chunk 分发器。
    
    Chat 和 Autonomous 都通过此类分发 streaming 事件，
    区别仅在于参数配置：
    - Chat: 有 websocket + client_id (直接发送 + 广播)
    - Autonomous: 仅广播 (无直接发送，所有输出走 session broadcast)
    """

    def __init__(
        self,
        task_id: str,
        session_id: str,
        task_type: str,  # "chat" | "autonomous"
        tracker,  # TaskTracker instance
        connection_manager,
        websocket: Optional[WebSocket] = None,
        client_id: Optional[str] = None,
        safe_send_fn: Optional[Callable] = None,
        broadcast_monitor_fn: Optional[Callable] = None,
        system_message_service=None,
    ):
        self.task_id = task_id
        self.session_id = session_id
        self.task_type = task_type
        self.tracker = tracker
        self.connection_manager = connection_manager
        self.websocket = websocket
        self.client_id = client_id
        self._safe_send = safe_send_fn
        self._broadcast_monitor_fn = broadcast_monitor_fn
        self._system_message_service = system_message_service

        # State
        self.chunk_count = 0
        self.client_gone = False
        self.has_error = False
        self.total_usage: Optional[Dict] = None

    def _mark_client_gone(self):
        """标记客户端已断开"""
        if not self.client_gone:
            self.client_gone = True
            tt = self.tracker.get(self.task_id)
            if tt:
                tt.client_sent_count = max(0, len(tt.chunks) - 1)

    async def _send_to_client(self, chunk: Dict) -> bool:
        """发送给当前 WebSocket 客户端"""
        if self.client_gone or not self.websocket or not self._safe_send:
            return False
        ok = await self._safe_send(self.websocket, chunk)
        if not ok:
            self._mark_client_gone()
            return False
        return True

    async def _broadcast(self, chunk: Dict):
        """广播给 session 内其他客户端"""
        exclude = self.client_id if not self.client_gone else None
        await self.connection_manager.broadcast_to_session(
            self.session_id, chunk, exclude_client=exclude,
        )

    async def _broadcast_monitor(self, chunk: Dict):
        """广播监控事件"""
        if self._broadcast_monitor_fn:
            await self._broadcast_monitor_fn(
                self.session_id, self.task_id, chunk, task_type=self.task_type,
            )

    def _push_error(self, title: str, content: str, source: str = ""):
        """推送系统错误通知"""
        if not self._system_message_service:
            return
        try:
            self._system_message_service.add_error(
                title, content,
                source=source or f"{self.task_type}_stream",
                category="system_error",
            )
        except Exception as e:
            logger.warning(f"Failed to push error notification: {e}")

    async def dispatch_chunk(self, chunk: Dict[str, Any]) -> None:
        """
        处理单个 chunk：记录 → 发送 → 广播 → 监控。
        
        这是核心分发逻辑，Chat 和 Autonomous 共享。
        """
        self.chunk_count += 1
        chunk_type = chunk.get("type", "unknown")

        # 记录到 TaskTracker 缓冲
        self.tracker.record_chunk(self.task_id, chunk)

        # 发送给当前 WebSocket 客户端
        await self._send_to_client(chunk)

        # 广播给 session 内其他客户端
        await self._broadcast(chunk)

        # 广播监控事件（过滤重复类型）
        monitor_types = {
            "llm_request_start", "llm_request_end", "tool_call", "tool_result",
            "thinking", "content", "error", "action_plan", "action_result",
            "task_complete", "task_stopped", "phase_verify",
        }
        if chunk_type in monitor_types:
            await self._broadcast_monitor(chunk)

        # 错误追踪
        if chunk_type == "error":
            self.has_error = True
            err_msg = chunk.get("error") or chunk.get("message") or "未知错误"
            self._push_error(
                f"{'对话' if self.task_type == 'chat' else '自主任务'}执行错误",
                err_msg,
            )

    async def dispatch_stream(
        self,
        generator: AsyncGenerator[Dict[str, Any], None],
        *,
        on_chunk: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        """
        分发整个流：逐个 chunk 处理。

        Args:
            generator: 来自 chat_runner.run_stream() 或 autonomous_agent.run_autonomous()
            on_chunk: 可选的 chunk 后处理回调（用于 Chat 的 image 提取等特殊逻辑）
        """
        async for chunk in generator:
            chunk_type = chunk.get("type", "")

            # stream_end 仅记录 usage，不分发
            if chunk_type == "stream_end":
                self.total_usage = chunk.get("usage")
                continue

            await self.dispatch_chunk(chunk)

            # 调用自定义后处理
            if on_chunk:
                await on_chunk(chunk)

    async def send_done(self, model_name: Optional[str] = None) -> None:
        """发送 done 信号"""
        done_msg: Dict[str, Any] = {"type": "done"}
        if model_name:
            done_msg["model"] = model_name
        if self.total_usage:
            done_msg["usage"] = self.total_usage

        self.tracker.record_chunk(self.task_id, done_msg)
        await self._send_to_client(done_msg)
        await self._broadcast(done_msg)

        # 广播任务完成监控事件
        await self._broadcast_monitor({
            "type": "task_complete",
            "status": "completed",
            "timestamp": datetime.now().isoformat(),
        })

    async def send_stopped(self) -> None:
        """发送 stopped 信号"""
        stopped_msg = {"type": "stopped", "session_id": self.session_id}
        self.tracker.record_chunk(self.task_id, stopped_msg)
        await self._send_to_client(stopped_msg)
        await self._broadcast(stopped_msg)
        await self._broadcast_monitor({
            "type": "task_stopped",
            "reason": "cancelled",
            "timestamp": datetime.now().isoformat(),
        })

    async def send_error(self, error: str) -> None:
        """发送 error 信号"""
        err_chunk = {"type": "error", "message": error, "error": error}
        self.tracker.record_chunk(self.task_id, err_chunk)
        await self._send_to_client(err_chunk)
        await self._broadcast(err_chunk)
        await self._broadcast_monitor(err_chunk)

    async def cleanup(self, final_status) -> None:
        """清理：flush tracker"""
        if not self.client_gone:
            self.tracker.clear_chunks(self.task_id)
        await self.tracker.finish(self.task_id, final_status)
