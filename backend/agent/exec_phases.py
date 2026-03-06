"""
Execution Phase Tracker — v3.4
Implements the three-phase execution loop: Gather → Act → Verify

Each iteration of the autonomous agent is categorised into one of three phases:
  GATHER  — Information collection (read_file, list_directory, think, web_search …)
  ACT     — Irreversible / side-effect operations (run_shell, write_file, call_tool …)
  VERIFY  — Automated validation that the preceding Act succeeded (optional auto-check)

The tracker:
  1. Infers the current phase from the action type.
  2. Records per-phase stats for observability.
  3. Provides an automated post-action verify hook that runs a lightweight sanity
     check (file-exists, exit-code == 0, etc.) and appends the result to the
     messages list so the LLM sees it as a tool result.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase definitions
# ---------------------------------------------------------------------------

class ExecutionPhase(str, Enum):
    GATHER = "gather"    # Read / search / inspect
    ACT    = "act"       # Execute side-effects
    VERIFY = "verify"    # Validate result


# Map action_type → primary phase
_ACTION_PHASE_MAP: Dict[str, ExecutionPhase] = {
    # Gather
    "read_file":       ExecutionPhase.GATHER,
    "list_directory":  ExecutionPhase.GATHER,
    "get_system_info": ExecutionPhase.GATHER,
    "clipboard_read":  ExecutionPhase.GATHER,
    "think":           ExecutionPhase.GATHER,
    # Act
    "run_shell":            ExecutionPhase.ACT,
    "create_and_run_script":ExecutionPhase.ACT,
    "write_file":           ExecutionPhase.ACT,
    "move_file":            ExecutionPhase.ACT,
    "copy_file":            ExecutionPhase.ACT,
    "delete_file":          ExecutionPhase.ACT,
    "open_app":             ExecutionPhase.ACT,
    "close_app":            ExecutionPhase.ACT,
    "clipboard_write":      ExecutionPhase.ACT,
    "call_tool":            ExecutionPhase.ACT,
    # Finish
    "finish":          ExecutionPhase.VERIFY,   # treat finish as verify
}


def infer_phase(action_type: str) -> ExecutionPhase:
    """Determine the execution phase for a given action_type string."""
    return _ACTION_PHASE_MAP.get(action_type.lower(), ExecutionPhase.ACT)


# ---------------------------------------------------------------------------
# Per‑iteration record
# ---------------------------------------------------------------------------

@dataclass
class PhaseRecord:
    iteration:    int
    phase:        ExecutionPhase
    action_type:  str
    success:      bool
    verify_note:  str = ""          # auto‑verify message (if any)


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

@dataclass
class PhaseTracker:
    """Attached to a single task execution. Tracks phase transitions and stats."""

    records: List[PhaseRecord] = field(default_factory=list)
    _gather_count: int = 0
    _act_count:    int = 0
    _verify_count: int = 0

    def record(self, iteration: int, action_type: str, success: bool, verify_note: str = "") -> PhaseRecord:
        phase = infer_phase(action_type)
        rec = PhaseRecord(
            iteration=iteration,
            phase=phase,
            action_type=action_type,
            success=success,
            verify_note=verify_note,
        )
        self.records.append(rec)
        if phase == ExecutionPhase.GATHER:
            self._gather_count += 1
        elif phase == ExecutionPhase.ACT:
            self._act_count += 1
        else:
            self._verify_count += 1
        return rec

    def stats(self) -> Dict[str, Any]:
        return {
            "total": len(self.records),
            "gather": self._gather_count,
            "act":    self._act_count,
            "verify": self._verify_count,
            "phase_sequence": [
                {"iter": r.iteration, "phase": r.phase.value, "action": r.action_type, "ok": r.success}
                for r in self.records
            ],
        }

    def last_phase(self) -> Optional[ExecutionPhase]:
        return self.records[-1].phase if self.records else None


# ---------------------------------------------------------------------------
# Automated Verify hooks
# ---------------------------------------------------------------------------

async def auto_verify(action_type: str, params: Dict[str, Any], result: Any) -> str:
    """
    Run a lightweight post-action sanity check and return a human-readable note.
    Returns an empty string when no check is applicable or when everything is fine.
    """
    action_type_lower = action_type.lower()

    # ---- write_file verify ----
    if action_type_lower == "write_file":
        path = params.get("path", "")
        if path:
            path = os.path.expanduser(path)
            if os.path.exists(path):
                size = os.path.getsize(path)
                return f"[Verify] write_file OK — 文件已存在，大小 {size} 字节: {path}"
            else:
                return f"[Verify] write_file WARN — 文件写入后未找到: {path}"

    # ---- move_file / copy_file verify ----
    if action_type_lower in ("move_file", "copy_file"):
        dest = params.get("destination", "") or params.get("dest", "")
        if dest:
            dest = os.path.expanduser(dest)
            if os.path.exists(dest):
                return f"[Verify] {action_type_lower} OK — 目标已存在: {dest}"
            else:
                return f"[Verify] {action_type_lower} WARN — 目标未找到: {dest}"

    # ---- delete_file verify ----
    if action_type_lower == "delete_file":
        path = params.get("path", "")
        if path:
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                return f"[Verify] delete_file OK — 文件已删除: {path}"
            else:
                return f"[Verify] delete_file WARN — 文件仍然存在: {path}"

    # ---- run_shell verify ----
    if action_type_lower == "run_shell":
        result_data = getattr(result, "data", None) or {}
        if isinstance(result_data, dict):
            exit_code = result_data.get("exit_code", 0)
            if exit_code != 0:
                return f"[Verify] run_shell WARN — 退出码 {exit_code}"
            return f"[Verify] run_shell OK — 退出码 0"

    return ""


def build_verify_message(verify_note: str, phase: ExecutionPhase) -> Optional[Dict[str, str]]:
    """
    Wrap a verify note as an assistant message so the LLM can see it in context.
    Returns None if the note is empty.
    """
    if not verify_note:
        return None
    return {
        "role": "user",
        "content": f"**[Phase: {phase.value.upper()}]** {verify_note}",
    }
