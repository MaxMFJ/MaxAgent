"""
Duck Registry — 分身 Agent 注册中心

管理所有已注册 Duck 实例的 CRUD、心跳检测、以及持久化。
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.duck_protocol import (
    DuckInfo,
    DuckStatus,
    DuckType,
)

logger = logging.getLogger(__name__)

# 持久化文件
DATA_DIR = Path(__file__).parent.parent / "data"
DUCK_REGISTRY_FILE = DATA_DIR / "duck_registry.json"

# 心跳超时 (秒)
HEARTBEAT_TIMEOUT = 60


class DuckRegistry:
    """Duck 注册中心 (单例)"""

    _instance: Optional["DuckRegistry"] = None

    def __init__(self):
        self._ducks: Dict[str, DuckInfo] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "DuckRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 初始化 ──────────────────────────────────────

    async def initialize(self):
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return
            self._load_from_disk()
            self._loaded = True

    def _load_from_disk(self):
        if not DUCK_REGISTRY_FILE.exists():
            return
        try:
            raw = json.loads(DUCK_REGISTRY_FILE.read_text(encoding="utf-8"))
            for item in raw:
                info = DuckInfo(**item)
                info.status = DuckStatus.OFFLINE  # 启动后所有 Duck 默认离线
                self._ducks[info.duck_id] = info
            logger.info(f"Duck Registry loaded {len(self._ducks)} ducks from disk")
        except Exception as e:
            logger.warning(f"Failed to load duck registry: {e}")

    def _save_to_disk(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = [d.model_dump() for d in self._ducks.values()]
        DUCK_REGISTRY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ─── CRUD ────────────────────────────────────────

    async def register(self, info: DuckInfo) -> DuckInfo:
        """注册或更新一个 Duck"""
        async with self._lock:
            info.last_heartbeat = time.time()
            info.status = DuckStatus.ONLINE
            existing = self._ducks.get(info.duck_id)
            if existing:
                # 保留统计与 LLM 配置（worker 重连时可能不携带 llm_config）
                info.completed_tasks = existing.completed_tasks
                info.failed_tasks = existing.failed_tasks
                info.registered_at = existing.registered_at
                if info.llm_api_key is None and existing.llm_api_key:
                    info.llm_api_key = existing.llm_api_key
                if info.llm_base_url is None and existing.llm_base_url:
                    info.llm_base_url = existing.llm_base_url
                if info.llm_model is None and existing.llm_model:
                    info.llm_model = existing.llm_model
            self._ducks[info.duck_id] = info
            self._save_to_disk()
            logger.info(f"Duck registered: {info.duck_id} ({info.name})")
            return info

    async def unregister(self, duck_id: str) -> bool:
        async with self._lock:
            if duck_id not in self._ducks:
                return False
            del self._ducks[duck_id]
            self._save_to_disk()
            logger.info(f"Duck unregistered: {duck_id}")
            return True

    async def get(self, duck_id: str) -> Optional[DuckInfo]:
        return self._ducks.get(duck_id)

    async def list_all(self) -> List[DuckInfo]:
        return list(self._ducks.values())

    async def list_online(self) -> List[DuckInfo]:
        return [d for d in self._ducks.values() if d.status == DuckStatus.ONLINE]

    async def list_available(self, duck_type: Optional[DuckType] = None) -> List[DuckInfo]:
        """列出空闲且在线的 Duck, 可按类型过滤"""
        result = []
        for d in self._ducks.values():
            if d.status != DuckStatus.ONLINE:
                continue
            if duck_type and d.duck_type != duck_type:
                continue
            result.append(d)
        return result

    # ─── 心跳 / 状态 ─────────────────────────────────

    async def heartbeat(self, duck_id: str) -> bool:
        duck = self._ducks.get(duck_id)
        if not duck:
            return False
        duck.last_heartbeat = time.time()
        if duck.status == DuckStatus.OFFLINE:
            duck.status = DuckStatus.ONLINE
        return True

    async def set_status(self, duck_id: str, status: DuckStatus):
        duck = self._ducks.get(duck_id)
        if duck:
            duck.status = status

    async def set_current_task(self, duck_id: str, task_id: Optional[str], busy_reason: Optional[str] = None):
        duck = self._ducks.get(duck_id)
        if duck:
            duck.current_task_id = task_id
            duck.busy_reason = busy_reason if task_id else None
            duck.status = DuckStatus.BUSY if task_id else DuckStatus.ONLINE

    async def update_llm_config(self, duck_id: str, **kwargs: Any) -> bool:
        """更新分身 LLM 配置（用户手动填写），仅更新传入的字段。空字符串会清空该字段。"""
        async with self._lock:
            duck = self._ducks.get(duck_id)
            if not duck:
                return False
            if "api_key" in kwargs:
                duck.llm_api_key = kwargs["api_key"] or None
            if "base_url" in kwargs:
                duck.llm_base_url = kwargs["base_url"] or None
            if "model" in kwargs:
                duck.llm_model = kwargs["model"] or None
            self._save_to_disk()
            logger.info(f"Duck {duck_id} LLM config updated")
            return True

    async def increment_completed(self, duck_id: str):
        duck = self._ducks.get(duck_id)
        if duck:
            duck.completed_tasks += 1
            self._save_to_disk()

    async def increment_failed(self, duck_id: str):
        duck = self._ducks.get(duck_id)
        if duck:
            duck.failed_tasks += 1
            self._save_to_disk()

    # ─── 心跳超时巡检 ────────────────────────────────

    async def check_heartbeats(self) -> List[str]:
        """标记心跳超时的 Duck 为离线, 返回超时的 duck_id 列表"""
        now = time.time()
        timed_out = []
        for duck in self._ducks.values():
            if duck.status != DuckStatus.OFFLINE and (now - duck.last_heartbeat) > HEARTBEAT_TIMEOUT:
                duck.status = DuckStatus.OFFLINE
                duck.current_task_id = None
                timed_out.append(duck.duck_id)
                logger.warning(f"Duck heartbeat timeout: {duck.duck_id}")
        return timed_out
