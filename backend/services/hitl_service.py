"""
HITL（Human-in-the-Loop）人工审批服务
关键动作需用户确认后才执行。通过 asyncio.Event 实现暂停/恢复。
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from services.audit_service import append_audit_event

logger = logging.getLogger(__name__)


class HitlDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class HitlRequest:
    __slots__ = (
        "action_id", "task_id", "session_id", "action_type",
        "params_summary", "risk_level", "created_at",
        "decision", "event",
    )

    def __init__(
        self,
        action_id: str,
        task_id: str,
        session_id: str,
        action_type: str,
        params_summary: str,
        risk_level: str = "medium",
    ):
        self.action_id = action_id
        self.task_id = task_id
        self.session_id = session_id
        self.action_type = action_type
        self.params_summary = params_summary
        self.risk_level = risk_level
        self.created_at = time.time()
        self.decision = HitlDecision.PENDING
        self.event = asyncio.Event()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "params_summary": self.params_summary,
            "risk_level": self.risk_level,
            "created_at": self.created_at,
            "decision": self.decision.value,
        }


# 高危动作关键词
_HIGH_RISK_COMMANDS = frozenset({"sudo", "rm ", "rm\t", "chmod", "chown", "kill", "pkill", "shutdown", "reboot"})
# 需要确认的动作类型
_CONFIRM_ACTION_TYPES = frozenset({"run_shell", "create_and_run_script", "delete_file", "move_file"})


def _classify_risk(action_type: str, params: Dict[str, Any]) -> str:
    """判断动作风险等级：high / medium / low / safe"""
    if action_type in ("read_file",):
        return "safe"
    if action_type == "write_file":
        path = (params.get("path") or "").lower()
        if any(path.startswith(p) for p in ("/system", "/library", "/usr", "/bin", "/sbin")):
            return "high"
        return "low"
    if action_type in ("delete_file", "move_file"):
        return "medium"
    if action_type in ("run_shell", "create_and_run_script"):
        cmd = (params.get("command") or params.get("code") or "").lower()
        if any(kw in cmd for kw in _HIGH_RISK_COMMANDS):
            return "high"
        return "medium"
    if action_type == "call_tool":
        tool_name = (params.get("tool_name") or "").lower()
        if tool_name in ("terminal", "run_shell", "shell"):
            args = params.get("args") or {}
            cmd = (args.get("command") or args.get("cmd") or "").lower()
            if any(kw in cmd for kw in _HIGH_RISK_COMMANDS):
                return "high"
            return "medium"
    return "safe"


def should_require_confirmation(action_type: str, params: Dict[str, Any]) -> bool:
    """判断是否需要 HITL 确认"""
    import app_state
    if not getattr(app_state, "ENABLE_HITL", False):
        return False
    risk = _classify_risk(action_type, params)
    return risk in ("high", "medium")


class HitlManager:
    """管理 HITL 确认请求的生命周期"""

    def __init__(self):
        self._pending: Dict[str, HitlRequest] = {}

    def create_request(
        self,
        action_id: str,
        task_id: str,
        session_id: str,
        action_type: str,
        params: Dict[str, Any],
    ) -> HitlRequest:
        """创建确认请求"""
        risk = _classify_risk(action_type, params)
        summary = _build_params_summary(action_type, params)
        req = HitlRequest(
            action_id=action_id,
            task_id=task_id,
            session_id=session_id,
            action_type=action_type,
            params_summary=summary,
            risk_level=risk,
        )
        self._pending[action_id] = req
        append_audit_event(
            "hitl_pending",
            task_id=task_id,
            session_id=session_id,
            action_type=action_type,
            params_summary=summary,
            risk_level=risk,
        )
        return req

    async def wait_for_decision(self, action_id: str) -> HitlDecision:
        """等待用户决定（阻塞，带超时）"""
        import app_state
        timeout = getattr(app_state, "HITL_CONFIRMATION_TIMEOUT", 120)
        req = self._pending.get(action_id)
        if req is None:
            return HitlDecision.REJECTED

        try:
            await asyncio.wait_for(req.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            req.decision = HitlDecision.TIMEOUT
            append_audit_event(
                "hitl_timeout",
                task_id=req.task_id,
                session_id=req.session_id,
                action_type=req.action_type,
                params_summary=req.params_summary,
                result="timeout",
                risk_level=req.risk_level,
            )

        decision = req.decision
        self._pending.pop(action_id, None)
        return decision

    def confirm(self, action_id: str) -> bool:
        """确认执行"""
        req = self._pending.get(action_id)
        if req is None:
            return False
        req.decision = HitlDecision.APPROVED
        req.event.set()
        append_audit_event(
            "hitl_approved",
            task_id=req.task_id,
            session_id=req.session_id,
            action_type=req.action_type,
            params_summary=req.params_summary,
            result="approved",
            risk_level=req.risk_level,
        )
        return True

    def reject(self, action_id: str) -> bool:
        """拒绝执行"""
        req = self._pending.get(action_id)
        if req is None:
            return False
        req.decision = HitlDecision.REJECTED
        req.event.set()
        append_audit_event(
            "hitl_rejected",
            task_id=req.task_id,
            session_id=req.session_id,
            action_type=req.action_type,
            params_summary=req.params_summary,
            result="rejected",
            risk_level=req.risk_level,
        )
        return True

    def get_pending(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询待确认请求"""
        reqs = self._pending.values()
        if session_id:
            reqs = [r for r in reqs if r.session_id == session_id]
        return [r.to_dict() for r in reqs]


def _build_params_summary(action_type: str, params: Dict[str, Any]) -> str:
    """简要描述参数（不含敏感完整内容）"""
    if action_type == "run_shell":
        return (params.get("command") or "")[:200]
    if action_type in ("write_file", "read_file", "delete_file"):
        return params.get("path", "")[:200]
    if action_type == "move_file":
        src = params.get("source", "")[:100]
        dst = params.get("destination", "")[:100]
        return f"{src} → {dst}"
    if action_type == "call_tool":
        tool = params.get("tool_name", "")
        args_keys = list((params.get("args") or {}).keys())
        return f"{tool}({', '.join(args_keys[:5])})"
    return str(params)[:200]


# 全局单例
_hitl_manager: Optional[HitlManager] = None


def get_hitl_manager() -> HitlManager:
    global _hitl_manager
    if _hitl_manager is None:
        _hitl_manager = HitlManager()
    return _hitl_manager
