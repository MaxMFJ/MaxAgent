"""
Environment State Manager — 运行时环境状态快照
不是 memory/history，而是当前环境的实时状态。
包括：文件系统变更、进程状态、剪贴板、焦点窗口等。
"""

import os
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FileState:
    """文件状态快照"""
    path: str
    exists: bool
    size: int = 0
    mtime: float = 0.0
    is_dir: bool = False

    @staticmethod
    def capture(path: str) -> "FileState":
        try:
            st = os.stat(path)
            return FileState(
                path=path,
                exists=True,
                size=st.st_size,
                mtime=st.st_mtime,
                is_dir=os.path.isdir(path),
            )
        except OSError:
            return FileState(path=path, exists=False)


@dataclass
class AppState:
    """应用程序状态"""
    name: str
    is_running: bool = False
    is_focused: bool = False
    window_title: str = ""
    pid: int = 0


@dataclass
class EnvironmentSnapshot:
    """完整环境快照"""
    cwd: str = ""
    focused_app: str = ""
    focused_window: str = ""
    clipboard_text: str = ""
    tracked_files: Dict[str, FileState] = field(default_factory=dict)
    running_apps: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cwd": self.cwd,
            "focused_app": self.focused_app,
            "focused_window": self.focused_window,
            "clipboard_preview": self.clipboard_text[:100] if self.clipboard_text else "",
            "tracked_files_count": len(self.tracked_files),
            "running_apps": self.running_apps[:10],
        }

    def for_llm(self) -> str:
        """生成简洁的环境状态给 LLM"""
        parts = []
        if self.cwd:
            parts.append(f"工作目录: {self.cwd}")
        if self.focused_app:
            app_info = self.focused_app
            if self.focused_window:
                app_info += f" - {self.focused_window}"
            parts.append(f"焦点窗口: {app_info}")
        if self.clipboard_text:
            preview = self.clipboard_text[:80].replace("\n", " ")
            parts.append(f"剪贴板: {preview}")
        return " | ".join(parts) if parts else "环境状态未知"


class EnvironmentStateManager:
    """
    管理运行时环境状态。
    - 在每次 action 前后捕获快照
    - 跟踪文件变更
    - 检测环境异常
    - 为 LLM 提供环境上下文
    """

    def __init__(self):
        self._current: EnvironmentSnapshot = EnvironmentSnapshot()
        self._previous: Optional[EnvironmentSnapshot] = None
        self._tracked_paths: Set[str] = set()
        self._cwd: str = ""
        self._history: List[Dict[str, Any]] = []  # 变更历史
        self._max_history = 50

    @property
    def current(self) -> EnvironmentSnapshot:
        return self._current

    def set_cwd(self, cwd: str) -> None:
        """设置当前工作目录"""
        self._cwd = cwd
        self._current.cwd = cwd

    def track_file(self, path: str) -> None:
        """添加要跟踪的文件路径"""
        self._tracked_paths.add(os.path.abspath(path))

    def track_files(self, paths: List[str]) -> None:
        for p in paths:
            self.track_file(p)

    def capture_snapshot(self) -> EnvironmentSnapshot:
        """捕获当前环境快照"""
        snap = EnvironmentSnapshot(
            cwd=self._cwd or os.getcwd(),
            timestamp=datetime.now(),
        )

        # 捕获被跟踪文件的状态
        for path in self._tracked_paths:
            snap.tracked_files[path] = FileState.capture(path)

        # 捕获焦点应用（通过 NSWorkspace）
        try:
            snap.focused_app, snap.focused_window = self._get_focused_app()
        except Exception:
            pass

        # 捕获剪贴板
        try:
            snap.clipboard_text = self._get_clipboard_text()
        except Exception:
            pass

        return snap

    def update(self) -> List[Dict[str, Any]]:
        """
        更新环境状态，返回检测到的变更列表。
        应在每次 action 执行后调用。
        """
        self._previous = self._current
        self._current = self.capture_snapshot()
        changes = self._detect_changes()
        if changes:
            self._history.extend(changes)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        return changes

    def pre_action_snapshot(self) -> EnvironmentSnapshot:
        """action 执行前的快照，用于对比"""
        return self.capture_snapshot()

    def post_action_diff(self, pre_snap: EnvironmentSnapshot) -> List[Dict[str, Any]]:
        """对比 action 前后的环境变化"""
        self._previous = pre_snap
        self._current = self.capture_snapshot()
        return self._detect_changes()

    def get_context_for_llm(self) -> str:
        """生成给 LLM 的环境上下文"""
        parts = [self._current.for_llm()]

        # 最近变更
        recent_changes = self._history[-5:] if self._history else []
        if recent_changes:
            change_strs = []
            for c in recent_changes:
                change_strs.append(f"  {c['type']}: {c['target']}")
            parts.append("最近环境变更:\n" + "\n".join(change_strs))

        return "\n".join(parts)

    def _detect_changes(self) -> List[Dict[str, Any]]:
        """检测两个快照之间的变化"""
        if not self._previous:
            return []
        changes = []
        prev = self._previous
        curr = self._current

        # 文件变更
        all_paths = set(prev.tracked_files.keys()) | set(curr.tracked_files.keys())
        for path in all_paths:
            old = prev.tracked_files.get(path)
            new = curr.tracked_files.get(path)
            if old and new:
                if not old.exists and new.exists:
                    changes.append({"type": "file_created", "target": path, "size": new.size})
                elif old.exists and not new.exists:
                    changes.append({"type": "file_deleted", "target": path})
                elif old.exists and new.exists and old.mtime != new.mtime:
                    changes.append({"type": "file_modified", "target": path,
                                    "old_size": old.size, "new_size": new.size})
            elif new and not old:
                if new.exists:
                    changes.append({"type": "file_created", "target": path, "size": new.size})

        # 焦点应用变更
        if prev.focused_app != curr.focused_app and curr.focused_app:
            changes.append({"type": "focus_changed",
                            "target": curr.focused_app,
                            "from": prev.focused_app})

        # 剪贴板变更
        if prev.clipboard_text != curr.clipboard_text and curr.clipboard_text:
            changes.append({"type": "clipboard_changed",
                            "target": curr.clipboard_text[:100]})

        return changes

    def _get_focused_app(self) -> tuple:
        """获取当前焦点应用名和窗口标题"""
        try:
            import subprocess
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get {name, title of first window} of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ", 1)
                app_name = parts[0] if parts else ""
                window_title = parts[1] if len(parts) > 1 else ""
                return app_name, window_title
        except Exception:
            pass
        return "", ""

    def _get_clipboard_text(self) -> str:
        """获取剪贴板文本"""
        try:
            import subprocess
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout[:500]
        except Exception:
            pass
        return ""

    def reset(self) -> None:
        self._current = EnvironmentSnapshot()
        self._previous = None
        self._tracked_paths.clear()
        self._history.clear()


# 单例
_instance: Optional[EnvironmentStateManager] = None


def get_environment_state() -> EnvironmentStateManager:
    global _instance
    if _instance is None:
        _instance = EnvironmentStateManager()
    return _instance
