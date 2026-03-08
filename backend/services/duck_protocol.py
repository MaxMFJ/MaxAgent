"""
Chow Duck — 分身 Agent 通信协议

定义主 Agent 与 Duck Agent 之间的消息类型和数据模型。
所有消息通过 WebSocket 以 JSON 格式传递。
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─── 消息类型 ─────────────────────────────────────────

class DuckMessageType(str, Enum):
    """Duck 通信消息类型"""
    # Duck → Main
    REGISTER = "register"           # Duck 注册
    HEARTBEAT = "heartbeat"         # 心跳
    RESULT = "result"               # 任务结果
    STATUS_REPORT = "status_report" # 状态上报

    # Main → Duck
    TASK = "task"                   # 任务下发
    CANCEL_TASK = "cancel_task"     # 取消任务
    PING = "ping"                   # 存活探测

    # 双向
    CHAT = "chat"                   # 自由对话
    ACK = "ack"                     # 确认


# ─── Duck 类型 ────────────────────────────────────────

class DuckType(str, Enum):
    """预定义 Duck 分身类型"""
    CRAWLER = "crawler"       # 爬虫鸭
    CODER = "coder"           # 编程鸭
    IMAGE = "image"           # 文生图鸭
    VIDEO = "video"           # 视频处理鸭
    TESTER = "tester"         # 测试鸭
    DESIGNER = "designer"     # 设计鸭
    GENERAL = "general"       # 通用鸭


# ─── Duck 状态 ────────────────────────────────────────

class DuckStatus(str, Enum):
    """Duck Agent 运行状态"""
    ONLINE = "online"         # 空闲, 可接任务
    BUSY = "busy"             # 正在执行任务
    OFFLINE = "offline"       # 离线


# ─── 任务状态 ─────────────────────────────────────────

class TaskStatus(str, Enum):
    """Duck 任务生命周期"""
    PENDING = "pending"       # 等待分配
    ASSIGNED = "assigned"     # 已分配, 等待 Duck 确认
    RUNNING = "running"       # 执行中
    COMPLETED = "completed"   # 完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


# ─── 基础消息 ─────────────────────────────────────────

class DuckMessage(BaseModel):
    """所有 Duck 消息的基础结构"""
    type: DuckMessageType
    msg_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    duck_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


# ─── 注册消息 ─────────────────────────────────────────

class DuckRegisterPayload(BaseModel):
    """REGISTER 消息 payload"""
    duck_type: DuckType = DuckType.GENERAL
    name: str = ""
    skills: List[str] = Field(default_factory=list)
    hostname: str = ""
    platform: str = ""          # darwin / linux / win32
    token: Optional[str] = None # Egg 中的认证 token


# ─── 任务消息 ─────────────────────────────────────────

class DuckTaskPayload(BaseModel):
    """TASK 消息 payload"""
    task_id: str
    description: str
    task_type: str = "general"
    params: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0           # 0=normal, 1=high, 2=urgent
    timeout: int = 600          # 秒


class DuckResultPayload(BaseModel):
    """RESULT 消息 payload"""
    task_id: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration: float = 0.0       # 执行耗时(秒)


# ─── Duck 信息 ────────────────────────────────────────

class DuckInfo(BaseModel):
    """Duck Agent 完整信息（存储在 Registry 中）"""
    duck_id: str
    name: str
    duck_type: DuckType
    status: DuckStatus = DuckStatus.OFFLINE
    skills: List[str] = Field(default_factory=list)
    hostname: str = ""
    platform: str = ""
    is_local: bool = False             # 是否为本地 Duck
    registered_at: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)
    current_task_id: Optional[str] = None
    busy_reason: Optional[str] = None  # "direct_chat" | "assigned_task" | None
    completed_tasks: int = 0
    failed_tasks: int = 0

    # 分身独立 LLM 配置（用户手动填写，用于专项任务更有效运用大模型）
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: Optional[str] = None


# ─── Duck 任务 ────────────────────────────────────────

class DuckTask(BaseModel):
    """完整任务记录"""
    task_id: str = Field(default_factory=lambda: f"dtask_{uuid.uuid4().hex[:8]}")
    description: str
    task_type: str = "general"
    params: Dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    timeout: int = 600

    # 分配
    assigned_duck_id: Optional[str] = None
    parent_task_id: Optional[str] = None   # 如果是子任务

    # 结果
    output: Any = None
    error: Optional[str] = None

    # 重试机制
    retry_count: int = 0                            # 当前已重试次数（调度器层面）
    max_retries: int = 2                            # 最大自动重试次数
    original_description: Optional[str] = None     # 保存原始任务描述（重试时增强用）
    retry_errors: List[str] = Field(default_factory=list)  # 每次失败的错误摘要

    # 时间
    created_at: float = Field(default_factory=time.time)
    assigned_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    last_activity: Optional[float] = None  # 最后一次活跃时间（chunk 产出时更新）
