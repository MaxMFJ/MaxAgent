"""
Action Recorder - 操作录制与回放
记录用户的 GUI/输入操作序列，支持保存和回放。
用于实现「录制回放」能力：记录用户操作序列 → 生成可复用的操作调用序列。
"""

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 录制数据存储目录
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECORDINGS_DIR = os.path.join(_BACKEND_ROOT, "data", "recordings")


@dataclass
class RecordedAction:
    """单条录制的操作"""

    tool: str  # 工具名称：gui_automation 或 input_control
    action: str  # 操作类型：click_element, type_text, keyboard_shortcut 等
    parameters: Dict[str, Any] = field(default_factory=dict)  # 操作参数
    timestamp: float = 0  # 录制时的时间戳
    delay_ms: int = 0  # 与上一条操作的间隔（ms），回放时使用


@dataclass
class Recording:
    """一次完整的录制"""

    id: str = ""
    name: str = ""
    description: str = ""
    actions: List[RecordedAction] = field(default_factory=list)
    created_at: float = 0
    updated_at: float = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "actions": [asdict(a) for a in self.actions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }


class ActionRecorder:
    """
    操作录制器：
    - start_recording: 开始录制
    - record_action: 记录一条操作
    - stop_recording: 停止并保存录制
    - replay: 回放录制的操作序列
    - list/get/delete: 管理录制
    """

    def __init__(self):
        self._active: Dict[str, Recording] = {}  # session_id -> 进行中的录制
        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    def start_recording(
        self,
        session_id: str = "default",
        name: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """开始一次新的录制，返回 recording_id"""
        if session_id in self._active:
            # 已有进行中的录制，先停止
            self.stop_recording(session_id)

        rec_id = f"rec_{uuid.uuid4().hex[:12]}"
        now = time.time()
        self._active[session_id] = Recording(
            id=rec_id,
            name=name or f"录制 {time.strftime('%Y-%m-%d %H:%M:%S')}",
            description=description,
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )
        logger.info(f"Recording started: {rec_id} (session={session_id})")
        return rec_id

    def record_action(
        self,
        session_id: str = "default",
        tool: str = "",
        action: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """记录一条操作到当前录制。返回是否成功。"""
        rec = self._active.get(session_id)
        if not rec:
            return False

        now = time.time()
        delay_ms = 0
        if rec.actions:
            delay_ms = int((now - rec.actions[-1].timestamp) * 1000)

        rec.actions.append(
            RecordedAction(
                tool=tool,
                action=action,
                parameters=parameters or {},
                timestamp=now,
                delay_ms=delay_ms,
            )
        )
        rec.updated_at = now
        return True

    def stop_recording(self, session_id: str = "default") -> Optional[Recording]:
        """停止录制并保存到磁盘，返回录制对象"""
        rec = self._active.pop(session_id, None)
        if not rec:
            return None

        rec.updated_at = time.time()
        self._save(rec)
        logger.info(
            f"Recording stopped: {rec.id}, {len(rec.actions)} actions saved"
        )
        return rec

    def is_recording(self, session_id: str = "default") -> bool:
        """是否正在录制"""
        return session_id in self._active

    def get_active_recording(self, session_id: str = "default") -> Optional[Recording]:
        """获取当前进行中的录制"""
        return self._active.get(session_id)

    def list_recordings(self) -> List[Dict[str, Any]]:
        """列出所有已保存的录制（不含 actions 详情）"""
        result = []
        if not os.path.isdir(RECORDINGS_DIR):
            return result
        for fname in sorted(os.listdir(RECORDINGS_DIR)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(RECORDINGS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result.append(
                    {
                        "id": data.get("id", ""),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "action_count": len(data.get("actions", [])),
                        "created_at": data.get("created_at", 0),
                        "tags": data.get("tags", []),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to read recording {fname}: {e}")
        return result

    def get_recording(self, recording_id: str) -> Optional[Recording]:
        """根据 ID 获取录制详情"""
        path = os.path.join(RECORDINGS_DIR, f"{recording_id}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load recording {recording_id}: {e}")
            return None

    def delete_recording(self, recording_id: str) -> bool:
        """删除一条录制"""
        path = os.path.join(RECORDINGS_DIR, f"{recording_id}.json")
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            logger.info(f"Recording deleted: {recording_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete recording {recording_id}: {e}")
            return False

    async def replay(
        self,
        recording_id: str,
        tool_executor,
        speed: float = 1.0,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        回放一条录制。

        Args:
            recording_id: 录制 ID
            tool_executor: 异步工具执行函数 async (tool_name, **params) -> ToolResult
            speed: 回放速度倍率（1.0=原速，2.0=两倍速）
            dry_run: 仅返回操作列表，不实际执行

        Returns:
            {"success": bool, "total": int, "executed": int, "failed": int, "results": [...]}
        """
        import asyncio

        rec = self.get_recording(recording_id)
        if not rec:
            return {"success": False, "error": f"录制 {recording_id} 不存在"}

        if not rec.actions:
            return {"success": True, "total": 0, "executed": 0, "failed": 0, "results": []}

        if dry_run:
            return {
                "success": True,
                "total": len(rec.actions),
                "dry_run": True,
                "actions": [asdict(a) for a in rec.actions],
            }

        results = []
        executed = 0
        failed = 0

        for i, act in enumerate(rec.actions):
            # 按录制间隔等待（根据速度倍率调整）
            if i > 0 and act.delay_ms > 0 and speed > 0:
                wait_sec = (act.delay_ms / 1000.0) / speed
                # 限制最大等待 5 秒，避免录制中的长间隔阻塞回放
                wait_sec = min(wait_sec, 5.0)
                await asyncio.sleep(wait_sec)

            try:
                params = dict(act.parameters)
                params["action"] = act.action
                result = await tool_executor(act.tool, **params)
                success = getattr(result, "success", True)
                results.append(
                    {
                        "step": i + 1,
                        "tool": act.tool,
                        "action": act.action,
                        "success": success,
                    }
                )
                if success:
                    executed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Replay step {i + 1} failed: {e}")
                results.append(
                    {
                        "step": i + 1,
                        "tool": act.tool,
                        "action": act.action,
                        "success": False,
                        "error": str(e),
                    }
                )
                failed += 1

        return {
            "success": failed == 0,
            "total": len(rec.actions),
            "executed": executed,
            "failed": failed,
            "results": results,
        }

    def _save(self, rec: Recording) -> None:
        """将录制保存到磁盘"""
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        path = os.path.join(RECORDINGS_DIR, f"{rec.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec.to_dict(), f, ensure_ascii=False, indent=2)

    @staticmethod
    def _from_dict(data: dict) -> Recording:
        """从字典恢复 Recording 对象"""
        actions = []
        for a in data.get("actions", []):
            actions.append(
                RecordedAction(
                    tool=a.get("tool", ""),
                    action=a.get("action", ""),
                    parameters=a.get("parameters", {}),
                    timestamp=a.get("timestamp", 0),
                    delay_ms=a.get("delay_ms", 0),
                )
            )
        return Recording(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            actions=actions,
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
            tags=data.get("tags", []),
        )


# ── 单例 ──────────────────────────────────────────────────────────────
_recorder: Optional[ActionRecorder] = None


def get_action_recorder() -> ActionRecorder:
    """获取全局 ActionRecorder 单例"""
    global _recorder
    if _recorder is None:
        _recorder = ActionRecorder()
    return _recorder
