[文件类型: .py] 共 892 行

[前 80 行]

"""
Local Duck Worker — 本地 Duck 运行时

在同一进程中以 asyncio 任务运行的 Duck Agent。
每个 Local Duck 有独立的任务队列，通过内存直接与调度器通信，
无需 WebSocket。
"""
from __future__ import annotations
import asyncio
import logging
import os
import platform
import socket
import time
import uuid
from typing import Any, Dict, Optional

from services.duck_protocol import (
    DuckInfo,
    DuckResultPayload,
    DuckStatus,
    DuckTask,
    DuckTaskPayload,
    DuckType,
    TaskStatus,
)
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)


class LocalDuckWorker:
    """单个本地 Duck 工作线程（asyncio 协程）"""

    def __init__(
        self,
        duck_id: str,
        name: str,
        duck_type: DuckType = DuckType.GENERAL,
        skills: list[str] | None = None,
        llm_api_key: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_provider_ref: Optional[str] = None,
    ):
        self.duck_id = duck_id
        self.name = name
        self.duck_type = duck_type
        self.skills = skills or []
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.llm_provider_ref = llm_provider_ref

        self._task_queue: asyncio.Queue[DuckTaskPayload] = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._agent = None  # 独立的 AutonomousAgent 实例（不再共享全局）

    # ─── 生命周期 ────────────────────────────────────

    async def start(self):
        """启动工作协程并注册到 Registry"""
        if self._running:
            return

        registry = DuckRegistry.get_instance()
        await registry.initialize()

        info = DuckInfo(
            duck_id=self.duck_id,
            name=self.name,
            duck_type=self.duck_type,
            status=DuckStatus.ONLINE,
            skills=self.skills,
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            is_local=True,
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,