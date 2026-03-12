[文件类型: .py] 共 1727 行

[前 80 行]

"""
主 WebSocket /ws 端点
将各消息类型分发到独立 handler 函数，保持可读性和可扩展性。
支持断线重连后任务恢复、服务端心跳保活。
"""
import asyncio
import json
import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app_state import (
    get_server_status, get_agent_core, get_autonomous_agent,
    get_llm_client, session_stream_tasks,
    get_task_tracker, AutoTaskStatus, TaskType,
    get_chat_runner, AUTO_DELEGATE_WHEN_MAIN_BUSY,
)
from task_persistence import get_persistence_manager, PersistentTaskStatus
from connection_manager import (
    connection_manager, safe_send_json, ClientType,
    remove_ws_write_lock,
)
from auth import verify_token

from agent.system_message_service import get_system_message_service, MessageCategory
from agent.episodic_memory import get_episodic_memory, get_strategy_db, Episode
from agent.model_selector import get_model_selector
from agent.local_llm_manager import get_local_llm_manager

try:
    from core.concurrency_limiter import get_concurrency_limiter
except ImportError:
    get_concurrency_limiter = None
try:
    from core.timeout_policy import get_timeout_policy
except ImportError:
    get_timeout_policy = None

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # 服务端心跳间隔（秒）

# ─── chat_to_duck 直聊回调映射 ──────────────────────────────────────────────
# task_id → WebSocket  （主 Backend 将 Duck 结果路由给请求发起方）
_duck_direct_chat_callbacks: dict[str, WebSocket] = {}


# ─── Duck 完成自动续步钩子 ───────────────────────────────────────────────────

async def _run_agent_and_broadcast_result(
    session_id: str,
    prompt: str,
    chat_runner,
    task_id: str,
    label: str = "Duck",
) -> None:
    """
    运行主 Agent（带工具执行能力），收集完整响应后作为 duck_task_complete 广播。
    解决：run_stream 产生的 chunk 消息在客户端空闲 WS 循环中无法被处理的问题。
    agent 可在此过程中使用 write_file / terminal 等工具实际执行任务。
    同时向监控面板广播 monitor_event，使主 Agent 执行过程可见。
    """
    # 生成一个钩子内任务 ID，用于监控面板追踪
    hook_task_id = f"duck_hook_{task_id}_{uuid.uuid4().hex[:6]}"

    # 广播任务开始事件到监控面板
    await broadcast_monitor_event(
        session_id, hook_task_id,
        {"type": "task_start", "task": prompt[:120], "timestamp": datetime.now().isoformat()},
        task_type="chat",
        worker_type="main",
        worker_id="main",
    )
