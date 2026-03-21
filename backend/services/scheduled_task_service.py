"""
Scheduled Task Service — 定时/周期任务引擎

基于 asyncio 的轻量级定时任务调度器：
- 支持 interval（间隔）和 cron（日/周/月定时）两种触发模式
- JSON 文件持久化，重启自动恢复
- 每次触发创建 Agent 任务并通过 WebSocket 推送结果
- 完整 CRUD: 创建、暂停、恢复、删除、查询

触发模式:
  interval:  {"every_seconds": 300}          — 每 5 分钟
  cron:      {"hour": 9, "minute": 0}        — 每天 09:00
  cron:      {"weekday": 0, "hour": 9}       — 每周一 09:00
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_SCHEDULE_FILE = _DATA_DIR / "scheduled_tasks.json"


# ─── Models ──────────────────────────────────────────

class TriggerType(str, Enum):
    INTERVAL = "interval"
    CRON = "cron"


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


@dataclass
class ScheduledTask:
    task_id: str
    description: str                  # Agent 任务描述（自然语言）
    trigger_type: TriggerType
    trigger_config: Dict[str, Any]    # interval: {every_seconds} / cron: {hour, minute, weekday?}
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    session_id: str = ""              # 关联会话（触发后推送结果）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    run_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger_type"] = self.trigger_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledTask":
        d = dict(d)
        d["trigger_type"] = TriggerType(d["trigger_type"])
        d["status"] = ScheduleStatus(d["status"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── Service ─────────────────────────────────────────

class ScheduledTaskService:
    """定时任务调度服务（单例）"""

    _instance: Optional["ScheduledTaskService"] = None

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._timers: Dict[str, asyncio.Task] = {}   # task_id → asyncio.Task
        self._running = False

    @classmethod
    def get_instance(cls) -> "ScheduledTaskService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Lifecycle ──

    async def start(self):
        """载入持久化任务并启动所有活跃调度"""
        self._load_from_disk()
        self._running = True
        for task in self._tasks.values():
            if task.status == ScheduleStatus.ACTIVE:
                self._start_timer(task)
        logger.info(f"[scheduler] Started with {len(self._timers)} active scheduled tasks")

    async def stop(self):
        """停止所有调度器"""
        self._running = False
        for tid, timer in list(self._timers.items()):
            timer.cancel()
        self._timers.clear()
        self._persist()
        logger.info("[scheduler] All scheduled tasks stopped")

    # ── CRUD ──

    def create_task(
        self,
        description: str,
        trigger_type: str,
        trigger_config: Dict[str, Any],
        session_id: str = "",
    ) -> ScheduledTask:
        task = ScheduledTask(
            task_id=f"sched_{uuid.uuid4().hex[:8]}",
            description=description,
            trigger_type=TriggerType(trigger_type),
            trigger_config=trigger_config,
            session_id=session_id,
        )
        task.next_run_at = self._calc_next_run(task)
        self._tasks[task.task_id] = task
        if self._running:
            self._start_timer(task)
        self._persist()
        logger.info(f"[scheduler] Created: {task.task_id} — {description}")
        return task

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[ScheduledTask]:
        return list(self._tasks.values())

    def pause_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = ScheduleStatus.PAUSED
        self._stop_timer(task_id)
        self._persist()
        return True

    def resume_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = ScheduleStatus.ACTIVE
        task.next_run_at = self._calc_next_run(task)
        if self._running:
            self._start_timer(task)
        self._persist()
        return True

    def delete_task(self, task_id: str) -> bool:
        task = self._tasks.pop(task_id, None)
        if not task:
            return False
        self._stop_timer(task_id)
        self._persist()
        logger.info(f"[scheduler] Deleted: {task_id}")
        return True

    # ── Timer Management ──

    def _start_timer(self, task: ScheduledTask):
        self._stop_timer(task.task_id)
        self._timers[task.task_id] = asyncio.create_task(
            self._timer_loop(task.task_id)
        )

    def _stop_timer(self, task_id: str):
        timer = self._timers.pop(task_id, None)
        if timer and not timer.done():
            timer.cancel()

    async def _timer_loop(self, task_id: str):
        """主调度循环：计算等待时间 → sleep → 执行 → 重复"""
        try:
            while self._running:
                task = self._tasks.get(task_id)
                if not task or task.status != ScheduleStatus.ACTIVE:
                    break

                wait = self._seconds_until_next(task)
                if wait > 0:
                    await asyncio.sleep(wait)

                # 再次检查（可能在 sleep 期间被暂停/删除）
                task = self._tasks.get(task_id)
                if not task or task.status != ScheduleStatus.ACTIVE:
                    break

                await self._execute_task(task)

                task.last_run_at = datetime.now().isoformat()
                task.run_count += 1
                task.next_run_at = self._calc_next_run(task)
                self._persist()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[scheduler] Timer loop error for {task_id}: {e}")

    async def _execute_task(self, task: ScheduledTask):
        """执行定时任务：创建 Agent 任务并推送 WebSocket 通知"""
        try:
            from connection_manager import connection_manager

            # 通知前端定时任务触发
            notification = {
                "type": "scheduled_task_triggered",
                "task_id": task.task_id,
                "description": task.description,
                "run_count": task.run_count + 1,
                "timestamp": datetime.now().isoformat(),
            }

            if task.session_id:
                await connection_manager.broadcast_to_session(
                    task.session_id, notification
                )
            else:
                await connection_manager.broadcast_all(notification)

            task.last_error = None
            logger.info(f"[scheduler] Triggered: {task.task_id} (run #{task.run_count + 1})")

        except Exception as e:
            task.last_error = str(e)[:200]
            logger.error(f"[scheduler] Execute error for {task.task_id}: {e}")

    # ── Time Calculations ──

    def _calc_next_run(self, task: ScheduledTask) -> str:
        """计算下一次执行时间（ISO 格式）"""
        now = datetime.now()

        if task.trigger_type == TriggerType.INTERVAL:
            seconds = task.trigger_config.get("every_seconds", 300)
            return (now + timedelta(seconds=seconds)).isoformat()

        # cron 模式
        hour = task.trigger_config.get("hour", 0)
        minute = task.trigger_config.get("minute", 0)
        weekday = task.trigger_config.get("weekday")  # 0=Monday

        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if weekday is not None:
            # 周定时：找下一个匹配的 weekday
            days_ahead = weekday - now.weekday()
            if days_ahead < 0 or (days_ahead == 0 and now >= target):
                days_ahead += 7
            target = target + timedelta(days=days_ahead)
        else:
            # 日定时：如果今天已过则推到明天
            if now >= target:
                target += timedelta(days=1)

        return target.isoformat()

    def _seconds_until_next(self, task: ScheduledTask) -> float:
        """距下次执行的秒数"""
        if not task.next_run_at:
            return 0
        try:
            next_dt = datetime.fromisoformat(task.next_run_at)
            diff = (next_dt - datetime.now()).total_seconds()
            return max(0, diff)
        except (ValueError, TypeError):
            return 0

    # ── Persistence ──

    def _persist(self):
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = [t.to_dict() for t in self._tasks.values()]
            _SCHEDULE_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[scheduler] Persist error: {e}")

    def _load_from_disk(self):
        if not _SCHEDULE_FILE.exists():
            return
        try:
            raw = json.loads(_SCHEDULE_FILE.read_text(encoding="utf-8"))
            for item in raw:
                task = ScheduledTask.from_dict(item)
                self._tasks[task.task_id] = task
            logger.info(f"[scheduler] Loaded {len(self._tasks)} scheduled tasks from disk")
        except Exception as e:
            logger.warning(f"[scheduler] Failed to load scheduled tasks: {e}")
