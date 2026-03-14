"""
ContextBuilder — 统一上下文构建基础设施

Chat 模式 (core.py) 与 Autonomous 模式 (autonomous_agent.py) 共享:
- 系统提示组装（base prompt + extra + evomap + project context）
- 用户上下文收集（时区、桌面路径、位置）
- 消息列表安全网（防止 current query 丢失）
- Duck 在线状态注入
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    统一的上下文构建器。
    """

    # ────────────────────── 系统提示组装 ──────────────────────

    @staticmethod
    def build_system_prompt(
        base_prompt: str,
        *,
        extra_system_prompt: str = "",
        evomap_context: str = "",
        project_context: str = "",
        gui_rules: str = "",
        user_context: str = "",
    ) -> str:
        """
        组装完整的系统提示。

        base_prompt: 基础系统提示（Chat 用 get_system_prompt_for_query，Autonomous 用 AUTONOMOUS_SYSTEM_PROMPT）
        其他参数按顺序拼接。
        """
        prompt = base_prompt

        # GUI 规则注入（Autonomous 模式的占位符替换）
        if "{gui_rules}" in prompt:
            prompt = prompt.replace("{gui_rules}", gui_rules)
        if "{user_context}" in prompt:
            prompt = prompt.replace("{user_context}", user_context)

        # 项目上下文前置
        if project_context:
            prompt = project_context + "\n\n---\n\n" + prompt

        # 额外系统提示 + EvoMap 追加
        combined_extra = "\n\n".join(p for p in [extra_system_prompt, evomap_context] if p)
        if combined_extra:
            prompt = f"{prompt}\n\n{combined_extra}"

        return prompt

    # ────────────────────── 消息安全网 ──────────────────────

    @staticmethod
    def ensure_user_message_present(
        messages: List[Dict[str, Any]],
        user_message: str,
    ) -> List[Dict[str, Any]]:
        """
        防污染安全网：确保当前 user message 一定在 messages 列表中。
        context_messages 可能因 token 截断丢失最新消息。
        """
        if not messages or messages[-1].get("role") == "user":
            return messages

        has_current_query = any(
            m.get("role") == "user"
            and m.get("content", "").strip() == user_message.strip()
            for m in messages[-3:]
        )
        if not has_current_query:
            logger.warning("Safety net: current user message missing from context, appending")
            messages = list(messages)
            messages.append({"role": "user", "content": user_message})

        return messages

    # ────────────────────── 用户上下文收集 ──────────────────────

    @staticmethod
    async def collect_user_context() -> str:
        """
        收集用户环境上下文（时区、桌面路径、位置等）。
        供系统提示注入。
        """
        parts: List[str] = []

        # 时区
        try:
            import datetime
            tz = datetime.datetime.now().astimezone().strftime("%Z %z")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            parts.append(f"当前时间: {now} ({tz})")
        except Exception:
            pass

        # 桌面路径（Duck 沙箱模式下替换为沙箱工作区路径）
        desktop = os.path.realpath(os.path.expanduser("~/Desktop"))
        try:
            from app_state import get_duck_context as _get_dc
            _dc = _get_dc()
            _sandbox_dir = (_dc or {}).get("sandbox_dir")
        except Exception:
            _sandbox_dir = None
        if _sandbox_dir:
            # Duck 沙箱模式：完全隐藏桌面路径，只暴露工作区路径
            parts.append(f"工作区路径: {_sandbox_dir}（所有输出必须保存到此路径）")
        else:
            parts.append(f"桌面路径: {desktop}")

        # 用户名
        user = os.environ.get("USER", "")
        if user:
            parts.append(f"用户名: {user}")

        # 语言/地区
        lang = os.environ.get("LANG", "")
        if lang:
            parts.append(f"系统语言: {lang}")

        return "\n".join(parts) if parts else ""

    # ────────────────────── Duck 在线状态注入 ──────────────────────

    @staticmethod
    async def get_duck_status_context() -> str:
        """
        获取在线 Duck 信息，供 LLM 上下文注入。
        """
        try:
            from app_state import IS_DUCK_MODE
            if IS_DUCK_MODE:
                return ""

            from services.duck_registry import DuckRegistry
            registry = DuckRegistry.get_instance()
            online = await registry.list_online()
            if online:
                duck_lines = []
                for d in online[:5]:
                    name = getattr(d, "name", getattr(d, "duck_id", "?"))
                    dtype = getattr(d, "duck_type", "general")
                    if hasattr(dtype, "value"):
                        dtype = dtype.value
                    duck_lines.append(f"  - {name} (类型: {dtype})")
                return (
                    f"【在线 Duck 分身】当前有 {len(online)} 个 Duck 可用:\n"
                    + "\n".join(duck_lines)
                    + "\n你可以用 delegate_duck 委派单个子任务，或用 delegate_dag 创建多Agent协作DAG（自动群聊）。"
                    + "\n当任务可分解为2+个有依赖关系的阶段时，优先使用 delegate_dag。"
                )
            else:
                return "【Duck 状态】当前没有在线 Duck，请自行完成所有子任务。"
        except Exception:
            return ""

    # ────────────────────── 重复验证检测提示 ──────────────────────

    @staticmethod
    def build_verification_hint(action_logs: list) -> Optional[str]:
        """
        检测 create_and_run_script 成功后多次 read_file/run_shell 验证 → 提示可直接 finish。
        """
        if len(action_logs) < 4:
            return None

        script_success_idx = None
        for i, log in enumerate(action_logs):
            at = log.action.action_type
            at_val = at.value if hasattr(at, "value") else str(at)
            if at_val == "create_and_run_script" and log.result.success:
                script_success_idx = i

        if script_success_idx is None:
            return None

        verify_types = {"read_file", "run_shell"}
        verify_count = sum(
            1 for log in action_logs[script_success_idx + 1:]
            if (log.action.action_type.value if hasattr(log.action.action_type, "value") else str(log.action.action_type)) in verify_types
        )
        if verify_count >= 2:
            return "【避免重复验证】你已多次 read_file/run_shell 验证，若文件已确认存在且内容正确，请直接 finish 完成任务。"
        return None
