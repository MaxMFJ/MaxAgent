"""
Observation Loop — 每次 action 前后自动观察环境变化
桥接 Action Executor、UI Grounding、Environment State。

职责：
1. Pre-action: 捕获环境快照（文件、焦点应用、剪贴板）
2. Post-action: 对比变化、UI 验证、生成结构化观察
3. 为 LLM 提供精简的环境反馈
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .action_result_schema import (
    ActionOutcome,
    ActionResult as StructuredActionResult,
    EnvironmentChange,
    UIObservation,
)
from .environment_state import EnvironmentStateManager, EnvironmentSnapshot
from .ui_grounding import UIGrounding, UISnapshot, get_ui_grounding

logger = logging.getLogger(__name__)


@dataclass
class Observation:
    """单次观察结果"""
    iteration: int = 0
    env_changes: List[Dict[str, Any]] = field(default_factory=list)
    ui_snapshot_text: str = ""
    verify_note: str = ""
    anomalies: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def for_llm(self, max_chars: int = 800) -> str:
        """生成给 LLM 的观察摘要"""
        parts = []

        if self.verify_note:
            parts.append(self.verify_note)

        if self.env_changes:
            change_strs = [f"  {c['type']}: {c['target']}" for c in self.env_changes[:5]]
            parts.append("环境变化:\n" + "\n".join(change_strs))

        if self.anomalies:
            parts.append("⚠ 异常: " + "; ".join(self.anomalies[:3]))

        if self.ui_snapshot_text:
            # 控制 UI 描述长度
            remaining = max_chars - sum(len(p) for p in parts) - 50
            if remaining > 100:
                parts.append(self.ui_snapshot_text[:remaining])

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    @property
    def has_changes(self) -> bool:
        return bool(self.env_changes or self.anomalies or self.verify_note)


class ObservationLoop:
    """
    Observation Loop — 在每次 action 前后运行观察。

    用法:
        loop = ObservationLoop(env_state=..., ui_grounding=...)

        # 执行前
        pre = await loop.pre_observe(iteration=1, action_type="write_file", params={...})

        # 执行 action ...

        # 执行后
        obs = await loop.post_observe(
            iteration=1,
            action_type="write_file",
            params={...},
            result=action_result,
            pre_snapshot=pre,
        )
        # obs.for_llm() → 注入到下一轮 LLM prompt
    """

    def __init__(
        self,
        env_state: Optional[EnvironmentStateManager] = None,
        ui_grounding: Optional[UIGrounding] = None,
    ):
        self._env = env_state or EnvironmentStateManager()
        self._ui = ui_grounding or get_ui_grounding()
        self._history: List[Observation] = []
        self._max_history = 30

    @property
    def env_state(self) -> EnvironmentStateManager:
        return self._env

    async def pre_observe(
        self,
        iteration: int,
        action_type: str,
        params: Dict[str, Any],
    ) -> EnvironmentSnapshot:
        """
        action 执行前的观察。
        - 跟踪 action 涉及的文件
        - 捕获环境快照
        返回快照，用于 post_observe 对比。
        """
        # 自动跟踪 action 涉及的文件
        self._auto_track_files(action_type, params)

        # 捕获快照
        snap = self._env.pre_action_snapshot()
        return snap

    async def post_observe(
        self,
        iteration: int,
        action_type: str,
        params: Dict[str, Any],
        result: Any,
        pre_snapshot: EnvironmentSnapshot,
        capture_ui: bool = False,
    ) -> Observation:
        """
        action 执行后的观察。
        - 对比文件/环境变化
        - 可选 UI 快照
        - 检测异常
        返回 Observation 供 LLM 消费。
        """
        obs = Observation(iteration=iteration)

        # 1. 环境变化检测
        try:
            env_changes = self._env.post_action_diff(pre_snapshot)
            obs.env_changes = env_changes
        except Exception as e:
            logger.debug("post_action_diff failed: %s", e)

        # 2. 自动验证（基于 action 类型和结果）
        obs.verify_note = self._auto_verify(action_type, params, result)

        # 3. 异常检测
        obs.anomalies = self._detect_anomalies(action_type, params, result)

        # 4. UI 快照（可选，仅 GUI 相关 action 时）
        if capture_ui or self._is_gui_action(action_type):
            try:
                ui_snap = await self._ui.capture_snapshot()
                if ui_snap.elements:
                    obs.ui_snapshot_text = ui_snap.for_llm(max_elements=15)
            except Exception as e:
                logger.debug("UI snapshot failed: %s", e)

        # 记录历史
        self._history.append(obs)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return obs

    def enrich_action_result(
        self,
        obs: Observation,
        structured_result: StructuredActionResult,
    ) -> StructuredActionResult:
        """
        将观察结果注入到 StructuredActionResult 中。
        """
        # 注入环境变更
        for c in obs.env_changes:
            structured_result.changes.append(
                EnvironmentChange(
                    change_type=c.get("type", "unknown"),
                    target=c.get("target", ""),
                    verified=True,
                )
            )

        # 注入验证结果
        if obs.verify_note:
            structured_result.verify_note = obs.verify_note
            structured_result.verified = True

        # 注入 UI 观察
        if obs.ui_snapshot_text:
            if structured_result.ui_observation is None:
                structured_result.ui_observation = UIObservation()
            structured_result.ui_observation.elements_summary = obs.ui_snapshot_text

        return structured_result

    def get_recent_observations_for_llm(self, n: int = 3, max_chars: int = 1500) -> str:
        """获取最近 N 次观察的摘要"""
        recent = [o for o in self._history[-n:] if o.has_changes]
        if not recent:
            return ""
        parts = []
        per_obs_budget = max_chars // max(len(recent), 1)
        for o in recent:
            text = o.for_llm(max_chars=per_obs_budget)
            if text:
                parts.append(f"[Step {o.iteration}] {text}")
        return "\n".join(parts)

    def reset(self) -> None:
        self._history.clear()
        self._env.reset()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auto_track_files(self, action_type: str, params: Dict[str, Any]) -> None:
        """根据 action 类型自动跟踪涉及的文件"""
        file_params = ["path", "file_path", "source", "destination", "dest", "save_path"]
        for key in file_params:
            val = params.get(key)
            if val and isinstance(val, str):
                self._env.track_file(val)

    def _auto_verify(self, action_type: str, params: Dict[str, Any], result: Any) -> str:
        """轻量级自动验证"""
        import os

        at = action_type.lower()
        success = getattr(result, "success", True)
        if isinstance(result, dict):
            success = result.get("success", True)

        if at == "write_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    return f"write_file OK — {size}B: {path}"
                elif success:
                    return f"write_file WARN — 声称成功但文件未找到: {path}"

        elif at in ("move_file", "copy_file"):
            dest = params.get("destination", "") or params.get("dest", "")
            if dest:
                dest = os.path.expanduser(dest)
                if os.path.exists(dest):
                    return f"{at} OK — 目标已存在: {dest}"
                elif success:
                    return f"{at} WARN — 目标未找到: {dest}"

        elif at == "delete_file":
            path = params.get("path", "")
            if path:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"delete_file OK — 已删除: {path}"
                elif success:
                    return f"delete_file WARN — 文件仍存在: {path}"

        elif at == "run_shell":
            result_data = getattr(result, "data", None) or getattr(result, "output", None) or {}
            if isinstance(result_data, dict):
                exit_code = result_data.get("exit_code", 0)
                if exit_code != 0:
                    return f"run_shell WARN — 退出码 {exit_code}"

        return ""

    def _detect_anomalies(
        self, action_type: str, params: Dict[str, Any], result: Any
    ) -> List[str]:
        """检测异常情况"""
        anomalies = []
        success = getattr(result, "success", True)
        if isinstance(result, dict):
            success = result.get("success", True)

        # 执行声称成功但环境无变化（写文件、移动文件等）
        side_effect_actions = {"write_file", "move_file", "copy_file", "delete_file", "create_and_run_script"}
        if action_type.lower() in side_effect_actions and success:
            # 如果后续 env_changes 为空，可能是假成功
            # 这个检查依赖 post_observe 中 env_changes 已填充
            pass  # 将在 enrich 时检查

        # 错误消息中的关键异常
        error = getattr(result, "error", None)
        if isinstance(result, dict):
            error = result.get("error")
        if error:
            error_lower = str(error).lower()
            if "permission denied" in error_lower:
                anomalies.append("权限不足")
            elif "no such file" in error_lower or "not found" in error_lower:
                anomalies.append("目标不存在")
            elif "timeout" in error_lower:
                anomalies.append("操作超时")
            elif "connection refused" in error_lower:
                anomalies.append("连接被拒绝")

        return anomalies

    def _is_gui_action(self, action_type: str) -> bool:
        """判断是否为 GUI 相关 action"""
        gui_actions = {
            "mouse_click", "mouse_double_click", "mouse_move",
            "keyboard_input", "keyboard_shortcut", "keyboard_hotkey",
            "open_app", "close_app", "call_tool",
            "gui_automation", "screenshot", "input_control",
        }
        return action_type.lower() in gui_actions


# 单例
_observation_loop: Optional[ObservationLoop] = None


def get_observation_loop() -> ObservationLoop:
    global _observation_loop
    if _observation_loop is None:
        _observation_loop = ObservationLoop()
    return _observation_loop
