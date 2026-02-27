"""
Terminal Session - 终端会话状态
同一 session 内复用 cwd、记录上一条命令输出，供后续命令和 prompt 注入使用。
"""

import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 当前执行上下文中的 session_id（由 core 在调用工具前设置）
_current_session_id: ContextVar[Optional[str]] = ContextVar("terminal_session_id", default=None)


def set_current_session_id(session_id: Optional[str]) -> None:
    """设置当前工具执行所属的 session_id"""
    _current_session_id.set(session_id)


def get_current_session_id() -> Optional[str]:
    """获取当前 session_id"""
    return _current_session_id.get(None)


@dataclass
class TerminalSessionState:
    """单会话的终端状态"""
    session_id: str
    last_cwd: str = ""
    last_command: str = ""
    last_stdout: str = ""
    last_stderr: str = ""
    last_exit_code: int = 0

    def get_context_hint(self, max_stdout_chars: int = 500) -> str:
        """生成注入到 prompt 的终端上下文提示"""
        if not self.last_command:
            return ""
        parts = []
        if self.last_cwd:
            parts.append(f"上条命令工作目录: {self.last_cwd}")
        parts.append(f"上条命令: {self.last_command}")
        if self.last_stdout:
            out = self.last_stdout[:max_stdout_chars]
            if len(self.last_stdout) > max_stdout_chars:
                out += "..."
            parts.append(f"上条输出: {out}")
        if self.last_stderr and self.last_exit_code != 0:
            err = self.last_stderr[:200]
            if len(self.last_stderr) > 200:
                err += "..."
            parts.append(f"上条错误: {err}")
        return "[终端上下文: " + "; ".join(parts) + "]"


class TerminalSessionStore:
    """终端会话状态存储"""

    def __init__(self):
        self._by_session: Dict[str, TerminalSessionState] = {}

    def get_or_create(self, session_id: str) -> TerminalSessionState:
        if session_id not in self._by_session:
            self._by_session[session_id] = TerminalSessionState(session_id=session_id)
        return self._by_session[session_id]

    def update(
        self,
        session_id: str,
        cwd: str = "",
        command: str = "",
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
    ) -> None:
        state = self.get_or_create(session_id)
        if cwd:
            state.last_cwd = cwd
        if command:
            state.last_command = command
        state.last_stdout = stdout
        state.last_stderr = stderr
        state.last_exit_code = exit_code
        logger.debug(f"Terminal session updated: {session_id}, cwd={state.last_cwd}")

    def get_context_hint(self, session_id: Optional[str]) -> str:
        if not session_id:
            return ""
        state = self._by_session.get(session_id)
        if not state:
            return ""
        return state.get_context_hint()

    def get_default_cwd(self, session_id: Optional[str]) -> str:
        """获取会话的默认工作目录（上条命令的 cwd），若无则返回空"""
        if not session_id:
            return ""
        state = self._by_session.get(session_id)
        if not state or not state.last_cwd:
            return ""
        return state.last_cwd


_terminal_session_store: Optional[TerminalSessionStore] = None


def get_terminal_session_store() -> TerminalSessionStore:
    global _terminal_session_store
    if _terminal_session_store is None:
        _terminal_session_store = TerminalSessionStore()
    return _terminal_session_store
