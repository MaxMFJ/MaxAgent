"""
TaskGuidanceMixin — Layer 2 & 3: Strategy escalation detection, mid-loop reflection,
plan generation, task guidance (skill/capsule injection), and skill fallback.
Extracted from autonomous_agent.py.
"""

import json
import logging
from typing import List, Optional

from .action_schema import TaskContext
from .capsule_registry import get_capsule_registry
from .thinking_manager import ESCALATION_NORMAL, ESCALATION_FORCE_SWITCH, ESCALATION_SKILL_FALLBACK

logger = logging.getLogger(__name__)


class TaskGuidanceMixin:
    """Mixin providing strategy escalation, task guidance and planning for AutonomousAgent."""

    # ------------------------------------------------------------------
    # Layer 2: Repeated failure detection & forced strategy switch
    # ------------------------------------------------------------------

    def _detect_repeated_failure(self, context: TaskContext) -> int:
        """
        v3.1: 基于 embedding 相似度或 fallback 到 md5，判断重复失败并返回 escalation 等级。
        阈值从 app_state (ESCALATION_* ) 读取。
        现委托给统一的 ThinkingManager。
        """
        # 同步 app_state 阈值到 ThinkingManager
        try:
            from app_state import (
                ESCALATION_FORCE_AFTER_N,
                ESCALATION_SKILL_AFTER_N,
                ESCALATION_SIMILARITY_THRESHOLD,
            )
            self._thinking_manager._escalation_force_after_n = ESCALATION_FORCE_AFTER_N
            self._thinking_manager._escalation_skill_after_n = ESCALATION_SKILL_AFTER_N
            self._thinking_manager._escalation_similarity_threshold = ESCALATION_SIMILARITY_THRESHOLD
        except ImportError:
            pass
        return self._thinking_manager.detect_repeated_failure(context.action_logs)

    # ------------------------------------------------------------------
    # v3.6  Action dedup — 委托给统一的 ThinkingManager
    # ------------------------------------------------------------------

    def _check_action_dedup(self, action, context: TaskContext) -> bool:
        """委托给统一的 ThinkingManager。"""
        return self._thinking_manager.check_action_dedup(
            action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type),
            action.params,
            context.action_logs,
        )

    def _build_escalation_prompt(
        self, level: int, context: TaskContext, skill_guidance: str
    ) -> str:
        """Build the escalation injection text for _generate_action."""
        if level == ESCALATION_NORMAL:
            return ""

        recent_types = [
            log.action.action_type.value for log in context.action_logs[-5:]
        ]
        used_methods = ", ".join(dict.fromkeys(recent_types))

        parts: List[str] = []

        if level >= ESCALATION_FORCE_SWITCH:
            parts.append(
                f"⚠️ You have repeatedly tried similar methods but failed to complete the task.\n"
                f"Methods you've used: {used_methods}\n"
                f"You MUST use a completely different approach. Do NOT reuse any of the same commands or tools.\n"
                f"Consider: 1) Use a different tool or API  2) Try a different approach  3) Gather more information first"
            )

        if level >= ESCALATION_SKILL_FALLBACK and skill_guidance:
            parts.append(skill_guidance)

        return "\n\n".join(parts)

    async def _run_mid_loop_reflection(self, context: TaskContext) -> Optional[str]:
        """委托给统一的 ThinkingManager。"""
        try:
            from app_state import ENABLE_MID_LOOP_REFLECTION
            if not ENABLE_MID_LOOP_REFLECTION:
                return None
        except ImportError:
            pass
        recent = context.action_logs[-5:]
        if len(recent) < 2:
            return None
        recent_steps = [
            {
                "action_type": log.action.action_type.value,
                "success": log.result.success,
                "output_snippet": log.result.error or str(log.result.output or ""),
            }
            for log in recent
        ]
        return await self._thinking_manager.run_reflection(
            context.task_description, recent_steps
        )

    async def _generate_plan(self, task: str) -> List[str]:
        """委托给统一的 ThinkingManager。"""
        return await self._thinking_manager.generate_plan(task)

    # ------------------------------------------------------------------
    # Task-start: skill/capsule 扫描与工具提示（避免盲目 run_shell）
    # ------------------------------------------------------------------

    async def _build_task_guidance(self, task: str) -> str:
        """
        任务开始时构建指导：匹配的 skill/capsule + 工具与平台提示（如截图用 call_tool/screencapture）。
        注入到首轮 LLM 上下文，减少盲目 run_shell 错误命令（如 screenshot）。
        """
        parts: List[str] = []

        # 1) 工具与平台提示：截图等常见意图
        if any(k in task for k in ("截图", "截屏", "screenshot", "屏幕")):
            # 指定应用窗口截图（微信窗口、Safari窗口 等）：必须用 app_name，不要用 area:full
            app_window_hint = None
            app_name_map = [
                ("微信", "WeChat"), ("wechat", "WeChat"),
                ("Safari", "Safari"), ("safari", "Safari"),
                ("Chrome", "Google Chrome"), ("chrome", "Google Chrome"),
                ("浏览器", "Safari"), ("钉钉", "DingTalk"), ("飞书", "Lark"),
            ]
            for keyword, app_name in app_name_map:
                if keyword in task and ("窗口" in task or "应用" in task or "程序" in task):
                    app_window_hint = (
                        f"[App Window Screenshot] The user wants to capture the '{keyword}' window. Use app_name parameter to capture only that app's window; do NOT use area:\"full\"."
                        f" Example: call_tool params={{\"tool_name\":\"screenshot\",\"args\":{{\"action\":\"capture\",\"app_name\":\"{app_name}\"}}}}"
                    )
                    break
            if not app_window_hint and ("窗口" in task or "某应用" in task or "指定" in task and "截图" in task):
                app_window_hint = (
                    "[App Window Screenshot] The user wants to capture a specific app's window. Use app_name in args (e.g. app_name:\"WeChat\" for WeChat window); do NOT use area:\"full\" for full screen."
                )
            if app_window_hint:
                parts.append(app_window_hint)
            else:
                parts.append(
                    "[Screenshot] macOS has no 'screenshot' command. For full screen: call_tool params={\"tool_name\":\"screenshot\",\"args\":{\"action\":\"capture\",\"area\":\"full\"}}; "
                    "or run_shell: screencapture -x -t png /tmp/screenshot.png"
                )

        # 1b) 研究/投资/财报类任务：明确可用 web_search 获取实时数据
        if any(k in task for k in ("研究", "财报", "投资", "科技股", "股票", "新闻", "最新", "实时", "调研")):
            parts.append(
                "[Web Research] You have the web_search tool to search web pages, news, financial data, etc. For multi-source research prefer call_tool(tool_name=\"web_search\", args={\"action\":\"research\", \"query\":\"keywords\", \"language\":\"zh-CN\"}); for quick lookup use action=\"search\" or \"news\". Never refuse by saying you cannot fetch real-time data."
            )

        # 2) 扫描并注入匹配的 skill/capsule（本地注册表优先；N/A 时按需拉取）
        try:
            registry = get_capsule_registry()
            capsules = registry.find_capsule_by_task(task, limit=3, min_score=0.7) if len(registry) > 0 else []

            # 本地未命中，且当前开启了按需拉取 — 异步拉取（不阻塞本轮 LLM 调用）
            if not capsules:
                try:
                    from app_state import ENABLE_ON_DEMAND_SKILL_FETCH
                    if ENABLE_ON_DEMAND_SKILL_FETCH:
                        from .capsule_on_demand import search_and_fetch as _od_fetch
                        capsules = await _od_fetch(task, limit=3, min_score=0.5)
                except Exception as ode:
                    logger.debug(f"On-demand skill fetch skipped: {ode}")

            if capsules:
                parts.append("[Matched Skills] The following skills are relevant to the task; use call_tool to execute:")
                for cap in capsules[:3]:
                    # 从 capsule inputs schema 提取参数信息
                    inputs_hint = ""
                    cap_inputs = getattr(cap, 'inputs', None) or {}
                    if isinstance(cap_inputs, dict) and cap_inputs:
                        param_parts = []
                        for key, schema in cap_inputs.items():
                            desc = schema.get("description", "") if isinstance(schema, dict) else ""
                            default = schema.get("default") if isinstance(schema, dict) else None
                            if default is not None:
                                param_parts.append(f'"{ key}": "({desc}, default:{default})"')
                            else:
                                param_parts.append(f'"{key}": "({desc})"')
                        inputs_hint = "{" + ", ".join(param_parts) + "}"
                    else:
                        inputs_hint = '{"task": "..."}'
                    parts.append(
                        f"  - {cap.id}: {cap.description[:60]}… → "
                        f"call_tool(tool_name=\"capsule\", args={{\"action\":\"execute\", \"capsule_id\":\"{cap.id}\", \"inputs\":{inputs_hint}}})"
                    )
        except Exception as e:
            logger.debug(f"Capsule scan for task guidance: {e}")

        # v3.8: 注入匹配的技能包知识
        try:
            from .skill_pack import get_skill_pack_manager
            skill_injection = get_skill_pack_manager().get_prompt_injection(
                task, max_knowledge_chars=1500
            )
            if skill_injection:
                parts.append(skill_injection)
        except Exception as e:
            logger.debug(f"Skill pack injection failed: {e}")

        if not parts:
            return ""
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Layer 3: Skill / Capsule fallback
    # ------------------------------------------------------------------

    def _try_skill_fallback(self, task: str) -> str:
        """
        Search the CapsuleRegistry for skills relevant to the task.
        Returns formatted guidance text, or empty string if nothing found.

        Note: 按需拉取（async）在 _build_task_guidance 中处理；
              此方法为 escalation 层同步兜底，仅查本地注册表。
        """
        try:
            registry = get_capsule_registry()
            if len(registry) == 0:
                return ""

            capsules = registry.find_capsule_by_task(task, limit=3, min_score=1.0)
            if not capsules:
                return ""

            best = capsules[0]
            steps = best.get_steps()

            lines = [
                f"💡 System found a relevant skill to help complete the task:",
                f"Skill: {best.description}",
                f"Source: {best.source or 'local'}",
            ]

            if steps:
                lines.append("Suggested steps:")
                for i, step in enumerate(steps[:8], 1):
                    desc = step.get("description", "")
                    tool = step.get("tool", step.get("name", ""))
                    if desc:
                        lines.append(f"  {i}. {desc}")
                    elif tool:
                        args_str = json.dumps(step.get("args", step.get("parameters", {})), ensure_ascii=False)
                        lines.append(f"  {i}. Use tool {tool}: {args_str[:120]}")

            lines.append("Please refer to the above suggestions and adjust your execution strategy.")
            return "\n".join(lines)

        except Exception as e:
            logger.debug(f"Skill fallback lookup failed: {e}")
            return ""
