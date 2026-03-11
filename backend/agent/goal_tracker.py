"""
L1 — Goal Progress Tracker
============================
Non-LLM, rule-based progress estimation for task goals.
Tracks sub-goals, completed milestones, and overall progress
to inject concise status into LLM context.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass
class SubGoal:
    """A decomposed piece of the overall task."""
    id: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    progress: float = 0.0          # 0.0 ~ 1.0
    evidence: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def mark_in_progress(self) -> None:
        if self.status == GoalStatus.PENDING:
            self.status = GoalStatus.IN_PROGRESS
            self.started_at = time.time()

    def mark_completed(self, evidence_note: str = "") -> None:
        self.status = GoalStatus.COMPLETED
        self.progress = 1.0
        self.completed_at = time.time()
        if evidence_note:
            self.evidence.append(evidence_note)

    def mark_blocked(self, reason: str = "") -> None:
        self.status = GoalStatus.BLOCKED
        if reason:
            self.evidence.append(f"blocked: {reason}")


class GoalProgressTracker:
    """
    Tracks overall task progress via sub-goal decomposition.
    Two modes:
      1) Explicit sub-goals (from a planner or user)
      2) Implicit tracking via action log signals
    """

    def __init__(self, task_description: str = "") -> None:
        self._task_description = task_description
        self._sub_goals: Dict[str, SubGoal] = {}
        self._milestones: List[str] = []
        self._action_count: int = 0
        self._success_count: int = 0
        self._key_files: List[str] = []
        self._completed_actions: List[str] = []   # v3.6: 已成功执行的动作摘要
        self._created_at: float = time.time()

    # --------------------------------------------------
    # Sub-goal management
    # --------------------------------------------------

    def set_sub_goals(self, descriptions: List[str]) -> None:
        """Set sub-goals from a plan (replaces existing)."""
        self._sub_goals.clear()
        for i, desc in enumerate(descriptions):
            gid = f"g{i+1}"
            self._sub_goals[gid] = SubGoal(id=gid, description=desc)

    def add_sub_goal(self, description: str) -> str:
        gid = f"g{len(self._sub_goals)+1}"
        self._sub_goals[gid] = SubGoal(id=gid, description=description)
        return gid

    def update_sub_goal(
        self,
        goal_id: str,
        status: Optional[GoalStatus] = None,
        progress: Optional[float] = None,
        evidence: Optional[str] = None,
    ) -> None:
        sg = self._sub_goals.get(goal_id)
        if not sg:
            return
        if status == GoalStatus.IN_PROGRESS:
            sg.mark_in_progress()
        elif status == GoalStatus.COMPLETED:
            sg.mark_completed(evidence or "")
        elif status == GoalStatus.BLOCKED:
            sg.mark_blocked(evidence or "")
        elif status is not None:
            sg.status = status
        if progress is not None:
            sg.progress = min(max(progress, 0.0), 1.0)
        if evidence and status not in (GoalStatus.COMPLETED, GoalStatus.BLOCKED):
            sg.evidence.append(evidence)

    def get_current_sub_goal(self) -> Optional[SubGoal]:
        """Return the first non-completed, non-blocked sub-goal."""
        for sg in self._sub_goals.values():
            if sg.status in (GoalStatus.PENDING, GoalStatus.IN_PROGRESS):
                return sg
        return None

    # --------------------------------------------------
    # Implicit tracking from action results
    # --------------------------------------------------

    def record_action(
        self,
        action_type: str,
        success: bool,
        params: Optional[Dict] = None,
        output: str = "",
    ) -> None:
        """Feed action results for automatic milestone & progress updates."""
        self._action_count += 1
        if success:
            self._success_count += 1
        params = params or {}

        # v3.6: 记录成功动作的摘要，供 LLM 上下文显示
        if success:
            summary = self._summarize_action(action_type, params, output)
            if summary:
                self._completed_actions.append(summary)

        # Track key file artifacts
        for key in ("file_path", "path", "target_path"):
            fp = params.get(key, "")
            if fp and fp not in self._key_files:
                self._key_files.append(fp)

        # Auto-detect milestones
        milestone = self._detect_milestone(action_type, success, params, output)
        if milestone:
            self._milestones.append(milestone)

        # Auto-advance sub-goals based on action signals
        self._auto_advance_sub_goals(action_type, success, params, output)

    def _detect_milestone(
        self, action_type: str, success: bool, params: Dict, output: str
    ) -> Optional[str]:
        """Detect notable accomplishments from action results."""
        if not success:
            return None

        if action_type == "write_file":
            path = params.get("file_path", params.get("path", ""))
            return f"创建/修改文件: {path}" if path else None

        if action_type == "run_shell":
            cmd = params.get("command", "")
            # Detect build / test / install commands
            for keyword in ("build", "make", "npm run", "pip install", "cargo", "go build"):
                if keyword in cmd.lower():
                    return f"执行构建/安装: {cmd[:80]}"
            # Detect test runs
            for keyword in ("test", "pytest", "jest", "cargo test"):
                if keyword in cmd.lower():
                    return f"运行测试: {cmd[:80]}"

        if action_type == "open_app":
            app = params.get("app_name", "")
            return f"打开应用: {app}" if app else None

        return None

    def _auto_advance_sub_goals(
        self, action_type: str, success: bool, params: Dict, output: str
    ) -> None:
        """Heuristically advance sub-goals based on action outcomes."""
        if not self._sub_goals:
            return

        current = self.get_current_sub_goal()
        if not current:
            return

        # Mark in-progress if pending
        if current.status == GoalStatus.PENDING:
            current.mark_in_progress()

        # Heuristic: check if action output or params match sub-goal description
        desc_lower = current.description.lower()
        action_signal = f"{action_type} {str(params)} {output[:200]}".lower()

        # Keyword overlap scoring
        desc_words = set(re.findall(r'\w{3,}', desc_lower))
        signal_words = set(re.findall(r'\w{3,}', action_signal))
        if desc_words:
            overlap = len(desc_words & signal_words) / len(desc_words)
            if overlap > 0 and success:
                # Increase progress proportionally
                current.progress = min(current.progress + overlap * 0.3, 0.95)

    def add_milestone(self, description: str) -> None:
        self._milestones.append(description)

    # --------------------------------------------------
    # v3.6  Action summary for dedup context
    # --------------------------------------------------

    @staticmethod
    def _summarize_action(action_type: str, params: Dict, output: str) -> Optional[str]:
        """Return a short one-line summary of a successful action, or None to skip."""
        # Skip noisy read-only / think actions
        if action_type in ("think", "read_file", "list_directory", "get_system_info", "clipboard_read"):
            return None

        if action_type == "write_file":
            return f"写入文件: {params.get('path', '?')}"

        if action_type == "create_and_run_script":
            fn = params.get("filename", "script")
            return f"创建并执行脚本: {fn}"

        if action_type == "run_shell":
            cmd = (params.get("command") or "")[:80]
            return f"执行命令: {cmd}"

        if action_type == "delegate_duck":
            dtype = params.get("duck_type", "?")
            desc = (params.get("description") or "")[:60]
            return f"委派子任务({dtype}): {desc}"

        if action_type == "call_tool":
            tool = params.get("tool_name", "")
            args = params.get("args", {})
            act = args.get("action", "")
            if tool == "screenshot":
                return None  # 截图太频繁，不记录
            elem = args.get("element_name", "")
            text = (args.get("text") or args.get("content") or "")[:40]
            parts = [f"{tool}.{act}"]
            if elem:
                parts.append(elem)
            if text:
                parts.append(f'"{text}"')
            return f"工具调用: {' '.join(parts)}"

        if action_type == "open_app":
            return f"打开应用: {params.get('app_name', '?')}"

        if action_type == "close_app":
            return f"关闭应用: {params.get('app_name', '?')}"

        if action_type == "clipboard_write":
            return f"写入剪贴板"

        return None

    # --------------------------------------------------
    # Progress estimation
    # --------------------------------------------------

    @property
    def overall_progress(self) -> float:
        """Estimate 0.0~1.0 overall progress."""
        if self._sub_goals:
            # Weighted average of sub-goal progress
            total = len(self._sub_goals)
            done = sum(sg.progress for sg in self._sub_goals.values())
            return done / max(total, 1)
        else:
            # Heuristic: milestone count + success rate
            if self._action_count == 0:
                return 0.0
            milestone_factor = min(len(self._milestones) * 0.15, 0.6)
            success_factor = (self._success_count / self._action_count) * 0.3
            return min(milestone_factor + success_factor, 0.95)

    @property
    def completed_sub_goals(self) -> int:
        return sum(
            1 for sg in self._sub_goals.values()
            if sg.status == GoalStatus.COMPLETED
        )

    @property
    def total_sub_goals(self) -> int:
        return len(self._sub_goals)

    # --------------------------------------------------
    # LLM context
    # --------------------------------------------------

    def get_context_for_llm(self, max_chars: int = 1000) -> str:
        """Compact progress summary for LLM context injection."""
        lines = []
        pct = f"{self.overall_progress:.0%}"

        if self._sub_goals:
            completed = self.completed_sub_goals
            total = self.total_sub_goals
            lines.append(f"【任务进度】{pct} ({completed}/{total} 子目标完成)")
            current = self.get_current_sub_goal()
            if current:
                lines.append(f"  当前子目标: {current.description} ({current.progress:.0%})")
            # List remaining
            remaining = [
                sg for sg in self._sub_goals.values()
                if sg.status not in (GoalStatus.COMPLETED, GoalStatus.SKIPPED)
            ]
            if remaining and len(remaining) <= 5:
                for sg in remaining:
                    status_icon = {"pending": "○", "in_progress": "◉", "blocked": "✖"}.get(
                        sg.status.value, "?"
                    )
                    lines.append(f"  {status_icon} {sg.description}")
        else:
            lines.append(f"【任务进度】~{pct}")

        if self._milestones:
            recent = self._milestones[-3:]
            lines.append("  已完成里程碑:")
            for m in recent:
                lines.append(f"    ✓ {m}")

        if self._key_files:
            recent_files = self._key_files[-5:]
            lines.append(f"  关键文件: {', '.join(recent_files)}")

        # v3.6: 已完成动作列表 — 帮助 LLM 避免重复
        if self._completed_actions:
            recent_acts = self._completed_actions[-10:]
            lines.append("  【已完成的操作 — 请勿重复】")
            for a in recent_acts:
                lines.append(f"    ✓ {a}")

        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars - 3] + "..."
        return result

    def get_status_dict(self) -> Dict:
        """Structured status for API/UI consumption."""
        return {
            "overall_progress": round(self.overall_progress, 2),
            "sub_goals": [
                {
                    "id": sg.id,
                    "description": sg.description,
                    "status": sg.status.value,
                    "progress": round(sg.progress, 2),
                }
                for sg in self._sub_goals.values()
            ],
            "milestones": self._milestones[-10:],
            "action_count": self._action_count,
            "success_count": self._success_count,
            "key_files": self._key_files[-10:],
            "completed_actions": self._completed_actions[-15:],
        }

    def reset(self) -> None:
        self._sub_goals.clear()
        self._milestones.clear()
        self._action_count = 0
        self._success_count = 0
        self._key_files.clear()
        self._completed_actions.clear()
