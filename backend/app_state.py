"""
全局应用状态管理
集中管理 LLM clients、agent_core、autonomous_agent、server_status 等全局单例。
所有模块通过此文件的 getter/setter 访问共享状态，避免循环 import。
"""
import os
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Deque

import asyncio

logger = logging.getLogger(__name__)


# ============== Server Status ==============

class ServerStatus(str, Enum):
    NORMAL = "normal"
    UPGRADING = "upgrading"
    RESTARTING = "restarting"


# ============== Feature Flags ==============

ENABLE_EVOMAP: bool = os.environ.get("ENABLE_EVOMAP", "false").lower() == "true"
AUTO_TOOL_UPGRADE: bool = os.environ.get("MACAGENT_AUTO_TOOL_UPGRADE", "true").lower() == "true"
CLOUD_PROVIDERS = {"deepseek", "openai", "newapi"}


# ============== Task Tracker ==============

class AutoTaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"


class TaskType(str, Enum):
    AUTONOMOUS = "autonomous"
    CHAT = "chat"


@dataclass
class TrackedTask:
    """一个正在或已完成的任务（autonomous 或 chat）的状态快照"""
    task_id: str
    session_id: str
    task_description: str
    task_type: TaskType = TaskType.AUTONOMOUS
    status: AutoTaskStatus = AutoTaskStatus.RUNNING
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    asyncio_task: Optional[asyncio.Task] = None
    chunks: Deque[dict] = field(default_factory=lambda: deque(maxlen=500))


class TaskTracker:
    """
    管理所有任务（autonomous + chat）的生命周期。
    任务与 session_id 关联而非与 WebSocket 连接绑定，
    断线重连后可通过 session_id 恢复输出。
    autonomous 和 chat 使用独立的 session 索引，互不干扰。
    """

    def __init__(self, max_finished_tasks: int = 50):
        self._tasks: Dict[str, TrackedTask] = {}
        self._session_index: Dict[str, str] = {}       # autonomous
        self._chat_session_index: Dict[str, str] = {}   # chat
        self._max_finished = max_finished_tasks
        self._lock = asyncio.Lock()

    def _index_for(self, task_type: TaskType) -> Dict[str, str]:
        return self._chat_session_index if task_type == TaskType.CHAT else self._session_index

    async def register(
        self, task_id: str, session_id: str, description: str,
        asyncio_task: asyncio.Task,
        task_type: TaskType = TaskType.AUTONOMOUS,
    ) -> TrackedTask:
        async with self._lock:
            idx = self._index_for(task_type)
            if session_id in idx:
                old_id = idx[session_id]
                old = self._tasks.get(old_id)
                if old and old.status == AutoTaskStatus.RUNNING and old.asyncio_task:
                    old.asyncio_task.cancel()
                    old.status = AutoTaskStatus.STOPPED
                    old.finished_at = time.time()

            tt = TrackedTask(
                task_id=task_id,
                session_id=session_id,
                task_description=description,
                task_type=task_type,
                asyncio_task=asyncio_task,
            )
            self._tasks[task_id] = tt
            idx[session_id] = task_id
            self._evict_old()
            return tt

    def record_chunk(self, task_id: str, chunk: dict):
        tt = self._tasks.get(task_id)
        if tt:
            tt.chunks.append(chunk)

    async def finish(self, task_id: str, status: AutoTaskStatus):
        async with self._lock:
            tt = self._tasks.get(task_id)
            if tt:
                tt.status = status
                tt.finished_at = time.time()
                tt.asyncio_task = None

    def get_by_session(self, session_id: str, task_type: TaskType = TaskType.AUTONOMOUS) -> Optional[TrackedTask]:
        idx = self._index_for(task_type)
        task_id = idx.get(session_id)
        if task_id:
            return self._tasks.get(task_id)
        return None

    def get(self, task_id: str) -> Optional[TrackedTask]:
        return self._tasks.get(task_id)

    def get_buffered_chunks(self, task_id: str) -> List[dict]:
        tt = self._tasks.get(task_id)
        if tt:
            return list(tt.chunks)
        return []

    def _evict_old(self):
        finished = [
            (tid, t) for tid, t in self._tasks.items()
            if t.status != AutoTaskStatus.RUNNING
        ]
        if len(finished) > self._max_finished:
            finished.sort(key=lambda x: x[1].finished_at or 0)
            for tid, t in finished[: len(finished) - self._max_finished]:
                self._tasks.pop(tid, None)
                idx = self._index_for(t.task_type)
                if idx.get(t.session_id) == tid:
                    idx.pop(t.session_id, None)


task_tracker = TaskTracker()


def get_task_tracker() -> TaskTracker:
    return task_tracker


# ============== Global State (module-level singletons) ==============

server_status: ServerStatus = ServerStatus.NORMAL

llm_client = None           # 主模型（用户设置，用于 chat）
cloud_llm_client = None     # 云端模型（DeepSeek），自主任务选择"远程"时专用
local_llm_client = None     # Local LLM (Ollama/LM Studio)
agent_core = None
autonomous_agent = None
reflect_llm = None

# 会话级流任务：session_id -> asyncio.Task
session_stream_tasks: Dict[str, asyncio.Task] = {}


# ============== Getters / Setters ==============

def get_server_status() -> ServerStatus:
    return server_status


def set_server_status(status: ServerStatus):
    global server_status
    server_status = status


def get_llm_client():
    return llm_client


def set_llm_client(client):
    global llm_client
    llm_client = client


def get_cloud_llm_client():
    return cloud_llm_client


def set_cloud_llm_client(client):
    global cloud_llm_client
    cloud_llm_client = client


def get_local_llm_client():
    return local_llm_client


def set_local_llm_client(client):
    global local_llm_client
    local_llm_client = client


def get_agent_core():
    return agent_core


def set_agent_core(core):
    global agent_core
    agent_core = core


def get_autonomous_agent():
    return autonomous_agent


def set_autonomous_agent(agent):
    global autonomous_agent
    autonomous_agent = agent


def get_reflect_llm():
    return reflect_llm


def set_reflect_llm(client):
    global reflect_llm
    reflect_llm = client
