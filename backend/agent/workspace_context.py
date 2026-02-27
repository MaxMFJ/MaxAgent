"""
Workspace Context - 文件强关联
记录当前工作目录、用户打开/编辑的文件，注入到 system prompt 实现类似 Cursor 的文件关联。
MacAgentApp 通过 HTTP API 上报 workspace 信息。
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_workspace_store: Dict[str, "WorkspaceState"] = {}


@dataclass
class WorkspaceState:
    """单会话的 workspace 状态"""
    session_id: str
    cwd: str = ""
    open_files: List[str] = field(default_factory=list)
    last_updated: float = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "open_files": self.open_files,
            "last_updated": self.last_updated,
        }


class WorkspaceContext:
    """
    管理 workspace 上下文，供 prompt 注入。
    支持：上报 cwd、打开文件；获取 prompt 提示文本。
    """

    def __init__(self):
        self._by_session: Dict[str, WorkspaceState] = {}

    def update(
        self,
        session_id: str,
        cwd: Optional[str] = None,
        open_files: Optional[List[str]] = None,
    ) -> None:
        """更新会话的 workspace 状态"""
        import time
        if session_id not in self._by_session:
            self._by_session[session_id] = WorkspaceState(session_id=session_id)
        state = self._by_session[session_id]
        if cwd is not None:
            state.cwd = os.path.abspath(os.path.expanduser(cwd))
        if open_files is not None:
            state.open_files = [os.path.abspath(os.path.expanduser(p)) for p in open_files]
        state.last_updated = time.time()
        logger.debug(f"Workspace updated: session={session_id}, cwd={state.cwd}, files={len(state.open_files)}")

    def get(self, session_id: str) -> Optional[WorkspaceState]:
        """获取会话的 workspace 状态"""
        return self._by_session.get(session_id)

    def get_prompt_hint(self, session_id: Optional[str] = None) -> str:
        """
        生成注入到 system prompt 的 workspace 提示。
        若无有效数据则返回空字符串。
        """
        if not session_id:
            return ""
        state = self.get(session_id)
        if not state or (not state.cwd and not state.open_files):
            return ""
        parts = []
        if state.cwd:
            parts.append(f"当前工作目录: {state.cwd}")
        if state.open_files:
            files_str = ", ".join(os.path.basename(p) for p in state.open_files[:5])
            if len(state.open_files) > 5:
                files_str += f" 等{len(state.open_files)}个文件"
            parts.append(f"打开的文件: {files_str}")
        if not parts:
            return ""
        return f"[工作区上下文: {'; '.join(parts)}]"


_workspace_context: Optional[WorkspaceContext] = None


def get_workspace_context() -> WorkspaceContext:
    """获取全局 WorkspaceContext 单例"""
    global _workspace_context
    if _workspace_context is None:
        _workspace_context = WorkspaceContext()
    return _workspace_context
