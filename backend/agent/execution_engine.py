"""
ExecutionEngine — 统一工具/动作执行基础设施

Chat 模式 (core.py) 与 Autonomous 模式 (autonomous_agent.py) 共享:
- 安全校验 (validate_action_safe)
- 幂等缓存
- HITL 人工审批
- 审计日志
- 文件创建追踪
- delegate_duck 拦截（Autonomous 模式强制阻塞）
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from tools.base import ToolResult
from tools.router import execute_tool

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    统一执行引擎，封装工具调用的前置/后置处理。

    两种模式通过不同方式使用：
    - Chat: execute_tool_call(tool_name, args) → ToolResult
    - Autonomous: execute_action(action) → ActionResult（包装层在 autonomous_agent.py）
    """

    def __init__(self, *, registry=None, session_id: str = "default"):
        self._registry = registry
        self._session_id = session_id

    # ────────────────────── 工具执行（Chat 模式入口）──────────────────────

    async def execute_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        *,
        bind_target_fn: Optional[Callable] = None,
    ) -> ToolResult:
        """
        执行单个工具调用（Chat 模式）。
        封装 execute_tool + 文件追踪。
        """
        from .terminal_session import set_current_session_id
        set_current_session_id(self._session_id)
        try:
            result = await execute_tool(
                tool_name, args,
                registry=self._registry,
                bind_target_fn=bind_target_fn,
            )
        finally:
            set_current_session_id(None)
        return result

    # ────────────────────── 安全校验（Autonomous 模式入口）──────────────────────

    @staticmethod
    def validate_safe(action_type: str, params: Dict[str, Any]) -> tuple:
        """
        统一安全校验。

        Returns:
            (ok: bool, error: Optional[str])
        """
        try:
            from .safety import validate_action_safe as _validate
            # _validate 接受 AgentAction 对象；这里创建轻量 mock
            class _MockAction:
                def __init__(self, at, p):
                    self.action_type = at
                    self.params = p
            return _validate(_MockAction(action_type, params))
        except ImportError:
            return True, None

    # ────────────────────── 幂等缓存 ──────────────────────

    @staticmethod
    def check_idempotent_cache(action_type: str, params: Dict[str, Any]) -> Optional[Dict]:
        """检查幂等缓存，命中则返回缓存结果。"""
        try:
            from services.idempotent_service import get_cached_result
            return get_cached_result(action_type, params)
        except Exception:
            return None

    @staticmethod
    def store_idempotent_cache(action_type: str, params: Dict[str, Any], result: Dict) -> None:
        """存储幂等缓存。"""
        try:
            from services.idempotent_service import store_cached_result
            store_cached_result(action_type, params, result)
        except Exception:
            pass

    # ────────────────────── 审计日志 ──────────────────────

    @staticmethod
    def audit_event(
        event_type: str,
        *,
        task_id: str = "",
        session_id: str = "",
        action_type: str = "",
        params_summary: str = "",
        result: str = "",
        risk_level: str = "low",
        details: Optional[Dict] = None,
    ) -> None:
        """统一审计事件记录。"""
        try:
            from services.audit_service import append_audit_event
            append_audit_event(
                event_type,
                task_id=task_id,
                session_id=session_id,
                action_type=action_type,
                params_summary=params_summary,
                result=result,
                risk_level=risk_level,
                **({"details": details} if details else {}),
            )
        except Exception:
            pass

    # ────────────────────── 文件创建追踪 ──────────────────────

    @staticmethod
    def extract_created_files(tool_name: str, args: Dict[str, Any], result: ToolResult) -> List[str]:
        """
        从工具执行结果中提取创建/修改的文件路径。
        统一替代 core.py 的 _record_created_files 和 autonomous_agent.py 的 _extract_artifacts。
        """
        files: List[str] = []
        if not result.success or not isinstance(result.data, dict):
            return files
        if tool_name == "file_operations":
            action = (args or {}).get("action")
            if action in ("write", "create"):
                path = result.data.get("path")
                if path:
                    files.append(path)
            elif action in ("move", "copy"):
                dest = result.data.get("to")
                if dest:
                    files.append(dest)
        elif tool_name == "developer_tool":
            project_path = result.data.get("project_path")
            if project_path:
                files.append(project_path)
        return files
