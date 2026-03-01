"""
任务状态持久化模块
实现任务状态的磁盘存储、检查点机制和恢复功能。
"""
import os
import json
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# 持久化存储目录
TASK_STORE_DIR = Path(__file__).parent / "data" / "task_store"
CHECKPOINT_DIR = TASK_STORE_DIR / "checkpoints"
TASK_METADATA_DIR = TASK_STORE_DIR / "metadata"


class PersistentTaskStatus(str, Enum):
    """持久化任务状态"""
    PENDING = "pending"           # 等待执行
    RUNNING = "running"           # 执行中
    PAUSED = "paused"            # 暂停（客户端断开但未超时）
    COMPLETED = "completed"       # 完成
    ERROR = "error"              # 错误
    STOPPED = "stopped"          # 用户停止
    ORPHAN_TIMEOUT = "orphan_timeout"  # 孤儿任务超时取消


@dataclass
class ActionCheckpoint:
    """单个 action 的检查点"""
    iteration: int
    action_type: str
    params: Dict[str, Any]
    reasoning: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "action_type": self.action_type,
            "params": self.params,
            "reasoning": self.reasoning,
            "success": self.success,
            "output": self._serialize_output(self.output),
            "error": self.error,
            "timestamp": self.timestamp,
        }
    
    @staticmethod
    def _serialize_output(output: Any) -> Any:
        """序列化输出，处理不可 JSON 化的对象"""
        if output is None:
            return None
        if isinstance(output, (str, int, float, bool, list, dict)):
            return output
        if isinstance(output, bytes):
            return output.decode('utf-8', errors='replace')[:10000]  # 限制大小
        return str(output)[:10000]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionCheckpoint":
        return cls(
            iteration=data.get("iteration", 0),
            action_type=data.get("action_type", "unknown"),
            params=data.get("params", {}),
            reasoning=data.get("reasoning", ""),
            success=data.get("success", False),
            output=data.get("output"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class TaskCheckpoint:
    """任务检查点，用于恢复任务执行"""
    task_id: str
    session_id: str
    task_description: str
    status: PersistentTaskStatus
    current_iteration: int
    max_iterations: int
    action_checkpoints: List[ActionCheckpoint] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_client_disconnect_at: Optional[str] = None
    final_result: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "task_description": self.task_description,
            "status": self.status.value if isinstance(self.status, PersistentTaskStatus) else self.status,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "action_checkpoints": [cp.to_dict() for cp in self.action_checkpoints],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_client_disconnect_at": self.last_client_disconnect_at,
            "final_result": self.final_result,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskCheckpoint":
        status = data.get("status", "running")
        if isinstance(status, str):
            try:
                status = PersistentTaskStatus(status)
            except ValueError:
                status = PersistentTaskStatus.RUNNING
        
        return cls(
            task_id=data.get("task_id", ""),
            session_id=data.get("session_id", ""),
            task_description=data.get("task_description", ""),
            status=status,
            current_iteration=data.get("current_iteration", 0),
            max_iterations=data.get("max_iterations", 50),
            action_checkpoints=[
                ActionCheckpoint.from_dict(cp) for cp in data.get("action_checkpoints", [])
            ],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            last_client_disconnect_at=data.get("last_client_disconnect_at"),
            final_result=data.get("final_result"),
        )


class TaskPersistenceManager:
    """任务持久化管理器"""
    
    def __init__(self):
        self._ensure_dirs()
        self._lock = asyncio.Lock()
        # 孤儿任务超时时间（秒）- 客户端断开后多久取消任务
        self.orphan_timeout = int(os.environ.get("MACAGENT_ORPHAN_TASK_TIMEOUT", "600"))  # 默认 10 分钟
        # 内存缓存
        self._checkpoints: Dict[str, TaskCheckpoint] = {}
        # 孤儿任务定时器
        self._orphan_timers: Dict[str, asyncio.Task] = {}
        # 是否已初始化
        self._initialized = False
    
    async def initialize(self):
        """服务启动时初始化：加载所有检查点并处理未完成的任务"""
        if self._initialized:
            return
        
        await self._load_all_checkpoints()
        await self._mark_interrupted_tasks()
        self._initialized = True
        logger.info(f"TaskPersistenceManager initialized with {len(self._checkpoints)} checkpoints")
    
    async def _load_all_checkpoints(self):
        """从磁盘加载所有检查点到内存缓存"""
        if not CHECKPOINT_DIR.exists():
            return
        
        for checkpoint_file in CHECKPOINT_DIR.glob("*.json"):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                checkpoint = TaskCheckpoint.from_dict(data)
                self._checkpoints[checkpoint.task_id] = checkpoint
            except Exception as e:
                logger.warning(f"Failed to load checkpoint {checkpoint_file.name}: {e}")
    
    async def _mark_interrupted_tasks(self):
        """将服务重启时仍在运行的任务标记为中断状态"""
        for task_id, checkpoint in self._checkpoints.items():
            if checkpoint.status in (PersistentTaskStatus.RUNNING, PersistentTaskStatus.PAUSED):
                checkpoint.status = PersistentTaskStatus.STOPPED
                checkpoint.final_result = "任务因服务重启被中断，可通过「恢复任务」继续执行"
                await self.save_checkpoint(checkpoint, notify_on_failure=False)
                logger.info(f"Marked interrupted task: {task_id}")
    
    def _ensure_dirs(self):
        """确保存储目录存在"""
        TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        TASK_METADATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _checkpoint_path(self, task_id: str) -> Path:
        return CHECKPOINT_DIR / f"{task_id}.json"
    
    async def save_checkpoint(self, checkpoint: TaskCheckpoint, notify_on_failure: bool = True) -> bool:
        """保存任务检查点到磁盘
        
        Args:
            checkpoint: 要保存的检查点
            notify_on_failure: 失败时是否发送系统通知
            
        Returns:
            是否保存成功
        """
        MAX_RETRIES = 3
        last_error = None
        
        async with self._lock:
            for attempt in range(MAX_RETRIES):
                try:
                    checkpoint.updated_at = datetime.now().isoformat()
                    self._checkpoints[checkpoint.task_id] = checkpoint
                    
                    path = self._checkpoint_path(checkpoint.task_id)
                    
                    # 先写入临时文件，再原子重命名，防止写入中断导致文件损坏
                    temp_path = path.with_suffix('.tmp')
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
                    temp_path.replace(path)  # 原子操作
                    
                    logger.debug(f"Checkpoint saved: task_id={checkpoint.task_id}, iteration={checkpoint.current_iteration}")
                    return True
                except OSError as e:
                    last_error = e
                    logger.warning(f"Checkpoint save attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(0.5 * (attempt + 1))  # 简单退避
                except Exception as e:
                    last_error = e
                    logger.error(f"Failed to save checkpoint for {checkpoint.task_id}: {e}")
                    break  # 非 I/O 错误不重试
            
            # 所有重试都失败
            logger.error(f"All checkpoint save attempts failed for {checkpoint.task_id}: {last_error}")
            
            # 发送系统通知
            if notify_on_failure:
                try:
                    from agent.system_message_service import get_system_message_service, MessageCategory
                    get_system_message_service().add_error(
                        "检查点保存失败",
                        f"任务 {checkpoint.task_id[:8]} 的检查点无法保存到磁盘。\n"
                        f"错误: {last_error}\n"
                        f"任务可能无法在服务重启后恢复。",
                        source="task_persistence",
                        category=MessageCategory.SYSTEM_ERROR.value,
                    )
                except Exception:
                    pass
            
            return False
    
    async def load_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """从磁盘加载任务检查点"""
        # 先从内存缓存查找
        if task_id in self._checkpoints:
            return self._checkpoints[task_id]
        
        path = self._checkpoint_path(task_id)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            checkpoint = TaskCheckpoint.from_dict(data)
            self._checkpoints[checkpoint.task_id] = checkpoint
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint for {task_id}: {e}")
            return None
    
    async def load_checkpoint_by_session(self, session_id: str) -> Optional[TaskCheckpoint]:
        """根据 session_id 加载最新的任务检查点"""
        try:
            # 扫描所有检查点文件，找到匹配 session_id 且最新的
            latest: Optional[TaskCheckpoint] = None
            latest_time = ""
            
            for path in CHECKPOINT_DIR.glob("*.json"):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get("session_id") == session_id:
                        updated_at = data.get("updated_at", "")
                        if updated_at > latest_time:
                            latest_time = updated_at
                            latest = TaskCheckpoint.from_dict(data)
                except Exception:
                    continue
            
            if latest:
                self._checkpoints[latest.task_id] = latest
            return latest
        except Exception as e:
            logger.error(f"Failed to load checkpoint by session {session_id}: {e}")
            return None
    
    async def delete_checkpoint(self, task_id: str):
        """删除任务检查点"""
        async with self._lock:
            self._checkpoints.pop(task_id, None)
            path = self._checkpoint_path(task_id)
            if path.exists():
                path.unlink()
                logger.debug(f"Checkpoint deleted: {task_id}")
    
    async def update_action_checkpoint(
        self,
        task_id: str,
        iteration: int,
        action_type: str,
        params: Dict[str, Any],
        reasoning: str,
        success: bool,
        output: Any = None,
        error: Optional[str] = None,
    ) -> bool:
        """更新任务的 action 检查点"""
        checkpoint = await self.load_checkpoint(task_id)
        if not checkpoint:
            return False
        
        action_cp = ActionCheckpoint(
            iteration=iteration,
            action_type=action_type,
            params=params,
            reasoning=reasoning,
            success=success,
            output=output,
            error=error,
        )
        
        checkpoint.action_checkpoints.append(action_cp)
        checkpoint.current_iteration = iteration
        
        return await self.save_checkpoint(checkpoint)
    
    async def update_task_status(
        self,
        task_id: str,
        status: PersistentTaskStatus,
        final_result: Optional[str] = None,
    ) -> bool:
        """更新任务状态"""
        checkpoint = await self.load_checkpoint(task_id)
        if not checkpoint:
            return False
        
        checkpoint.status = status
        if final_result is not None:
            checkpoint.final_result = final_result
        
        return await self.save_checkpoint(checkpoint)
    
    async def mark_client_disconnected(self, session_id: str):
        """标记客户端断开，启动孤儿任务超时计时器"""
        checkpoint = await self.load_checkpoint_by_session(session_id)
        if not checkpoint or checkpoint.status != PersistentTaskStatus.RUNNING:
            return
        
        checkpoint.last_client_disconnect_at = datetime.now().isoformat()
        checkpoint.status = PersistentTaskStatus.PAUSED
        await self.save_checkpoint(checkpoint)
        
        # 启动超时计时器
        task_id = checkpoint.task_id
        if task_id in self._orphan_timers:
            self._orphan_timers[task_id].cancel()
        
        async def orphan_timeout_handler():
            try:
                await asyncio.sleep(self.orphan_timeout)
                # 检查是否仍然是孤儿状态
                cp = await self.load_checkpoint(task_id)
                if cp and cp.status == PersistentTaskStatus.PAUSED:
                    logger.info(f"Orphan task timeout, marking for cancellation: {task_id}")
                    cp.status = PersistentTaskStatus.ORPHAN_TIMEOUT
                    await self.save_checkpoint(cp)
            except asyncio.CancelledError:
                logger.debug(f"Orphan timer cancelled for task {task_id}")
            except Exception as e:
                logger.warning(f"Orphan timeout handler error for {task_id}: {e}")
            finally:
                # 清理定时器引用，防止内存泄漏
                self._orphan_timers.pop(task_id, None)
        
        self._orphan_timers[task_id] = asyncio.create_task(orphan_timeout_handler())
        logger.info(f"Orphan timer started for task {task_id}, timeout={self.orphan_timeout}s")
    
    async def mark_client_reconnected(self, session_id: str):
        """标记客户端重连，取消孤儿任务计时器"""
        checkpoint = await self.load_checkpoint_by_session(session_id)
        if not checkpoint:
            return
        
        task_id = checkpoint.task_id
        
        # 取消超时计时器
        if task_id in self._orphan_timers:
            self._orphan_timers[task_id].cancel()
            del self._orphan_timers[task_id]
            logger.info(f"Orphan timer cancelled for task {task_id}")
        
        # 如果是暂停状态，恢复为运行
        if checkpoint.status == PersistentTaskStatus.PAUSED:
            checkpoint.status = PersistentTaskStatus.RUNNING
            checkpoint.last_client_disconnect_at = None
            await self.save_checkpoint(checkpoint)
            logger.info(f"Task resumed from paused state: {task_id}")
    
    async def create_task_checkpoint(
        self,
        task_id: str,
        session_id: str,
        task_description: str,
        max_iterations: int = 50,
    ) -> TaskCheckpoint:
        """创建新的任务检查点"""
        checkpoint = TaskCheckpoint(
            task_id=task_id,
            session_id=session_id,
            task_description=task_description,
            status=PersistentTaskStatus.RUNNING,
            current_iteration=0,
            max_iterations=max_iterations,
        )
        await self.save_checkpoint(checkpoint)
        return checkpoint
    
    async def get_recoverable_tasks(self, session_id: str) -> List[TaskCheckpoint]:
        """获取可恢复的任务列表"""
        recoverable = []
        try:
            for path in CHECKPOINT_DIR.glob("*.json"):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if data.get("session_id") == session_id:
                        status = data.get("status", "")
                        # 可恢复的状态：运行中、暂停
                        if status in [PersistentTaskStatus.RUNNING.value, PersistentTaskStatus.PAUSED.value]:
                            recoverable.append(TaskCheckpoint.from_dict(data))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Failed to get recoverable tasks: {e}")
        
        return recoverable
    
    async def cleanup_old_checkpoints(self, max_age_days: int = 7):
        """清理过期的检查点"""
        now = datetime.now()
        cleaned = 0
        
        for path in CHECKPOINT_DIR.glob("*.json"):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                updated_at = data.get("updated_at", "")
                status = data.get("status", "")
                
                # 只清理已完成/错误/停止的任务
                if status not in [
                    PersistentTaskStatus.COMPLETED.value,
                    PersistentTaskStatus.ERROR.value,
                    PersistentTaskStatus.STOPPED.value,
                    PersistentTaskStatus.ORPHAN_TIMEOUT.value,
                ]:
                    continue
                
                if updated_at:
                    updated = datetime.fromisoformat(updated_at)
                    age = (now - updated).days
                    if age > max_age_days:
                        path.unlink()
                        cleaned += 1
            except Exception:
                continue
        
        if cleaned > 0:
            logger.info(f"Cleaned {cleaned} old checkpoints")


# 全局单例
_persistence_manager: Optional[TaskPersistenceManager] = None


def get_persistence_manager() -> TaskPersistenceManager:
    """获取持久化管理器单例"""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = TaskPersistenceManager()
    return _persistence_manager
