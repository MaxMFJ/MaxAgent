"""
Human Demo Recorder — 人工演示录制管理
管理人工 GUI 操作录制会话，事件由 Mac App 前端通过 API 推送。

架构：
  1. Mac App Swift 端通过 NSEvent.addGlobalMonitorForEvents 捕获全局鼠标/键盘事件
  2. 前端通过 POST /demos/event 实时推送事件到后端
  3. 后端负责事件存储、语义压缩和 LLM 学习
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from paths import DATA_DIR
from .human_demo_models import DemoStep, HumanDemoSession, HumanEvent

logger = logging.getLogger(__name__)

DEMOS_DIR = os.path.join(DATA_DIR, "human_demos")
DEMO_SCREENSHOTS_DIR = os.path.join(DATA_DIR, "demo_screenshots")


class HumanDemoRecorder:
    """
    人工演示录制器。

    事件由 Mac App 前端捕获并通过 REST API 推送，
    本模块负责会话管理、事件存储和持久化。
    """

    def __init__(self):
        self._active: Dict[str, HumanDemoSession] = {}  # session_id → 进行中的演示
        os.makedirs(DEMOS_DIR, exist_ok=True)

    # ── 录制控制 ──────────────────────────────────────────

    def start(
        self,
        session_id: str = "default",
        task_description: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """开始录制人工演示，返回 demo_id"""
        if session_id in self._active:
            self.stop(session_id)

        session = HumanDemoSession.new(task_description=task_description, tags=tags)
        self._active[session_id] = session

        logger.info(f"Human demo started: {session.id} (session={session_id})")
        return session.id

    def stop(self, session_id: str = "default") -> Optional[HumanDemoSession]:
        """停止录制，保存并返回会话"""
        session = self._active.pop(session_id, None)
        if not session:
            return None

        session.finished_at = time.time()
        session.duration_seconds = session.finished_at - session.created_at
        session.status = "finished"

        self._save(session)
        logger.info(
            f"Human demo stopped: {session.id}, {len(session.events)} events"
        )
        return session

    def is_recording(self, session_id: str = "default") -> bool:
        return session_id in self._active

    def get_active(self, session_id: str = "default") -> Optional[HumanDemoSession]:
        return self._active.get(session_id)

    # ── 手动事件追加（供前端/API 使用）──────────────────

    def add_event(
        self,
        session_id: str = "default",
        event_type: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """手动追加一条事件（API 用，例如前端发送自己捕获的事件）"""
        session = self._active.get(session_id)
        if not session:
            return False
        event = HumanEvent(type=event_type, timestamp=time.time(), data=data or {})
        session.events.append(event)
        return True

    # ── 持久化 ──────────────────────────────────────────

    def _save(self, session: HumanDemoSession):
        os.makedirs(DEMOS_DIR, exist_ok=True)
        path = os.path.join(DEMOS_DIR, f"{session.id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, demo_id: str) -> Optional[HumanDemoSession]:
        path = os.path.join(DEMOS_DIR, f"{demo_id}.json")
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return HumanDemoSession.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load demo {demo_id}: {e}")
            return None

    def save_session(self, session: HumanDemoSession):
        """公开保存方法（学习结果更新后调用）"""
        self._save(session)

    def list_demos(self) -> List[Dict[str, Any]]:
        result = []
        if not os.path.isdir(DEMOS_DIR):
            return result
        for fname in sorted(os.listdir(DEMOS_DIR)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(DEMOS_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = HumanDemoSession.from_dict(data)
                result.append(session.to_summary())
            except Exception as e:
                logger.warning(f"Failed to read demo {fname}: {e}")
        return result

    def delete_demo(self, demo_id: str) -> bool:
        path = os.path.join(DEMOS_DIR, f"{demo_id}.json")
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            # 也删截图目录
            screenshot_dir = os.path.join(DEMO_SCREENSHOTS_DIR, demo_id)
            if os.path.isdir(screenshot_dir):
                import shutil
                shutil.rmtree(screenshot_dir, ignore_errors=True)
            return True
        except Exception as e:
            logger.error(f"Failed to delete demo {demo_id}: {e}")
            return False


# ── 单例 ──────────────────────────────────────────────────────
_recorder: Optional[HumanDemoRecorder] = None


def get_human_demo_recorder() -> HumanDemoRecorder:
    global _recorder
    if _recorder is None:
        _recorder = HumanDemoRecorder()
    return _recorder
