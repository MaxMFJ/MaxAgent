"""
ThinkingManager — 统一思考逻辑基础设施

Chat 模式 (core.py) 与 Autonomous 模式 (autonomous_agent.py) 共享:
- 计划生成 (Plan-and-Execute)
- 中途反思 (Mid-loop reflection)
- 策略升级 (Escalation: NORMAL → FORCE_SWITCH → SKILL_FALLBACK)
- 重复失败检测
- 行为去重 (Action dedup)
- 循环检测 (Loop detection)
"""

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, FrozenSet

logger = logging.getLogger(__name__)

# ── 策略升级常量 ──
ESCALATION_NORMAL = 0
ESCALATION_FORCE_SWITCH = 1
ESCALATION_SKILL_FALLBACK = 2


class ThinkingManager:
    """
    统一的 Agent 思考管理器。

    两种模式通过相同的思考 API 调用：
    - generate_plan(): 任务拆解
    - should_reflect(): 是否需要中途反思
    - run_reflection(): 执行反思
    - detect_repeated_failure(): 策略升级检测
    - check_action_dedup(): 行为去重
    - detect_loop(): 循环检测
    """

    def __init__(self, llm_client=None, *, is_duck_mode: bool = False):
        self._llm = llm_client
        self.is_duck_mode = is_duck_mode
        # 可被外部更新
        self._escalation_force_after_n = 2
        self._escalation_skill_after_n = 3
        self._escalation_similarity_threshold = 0.85

    def update_llm(self, llm_client):
        """更新 LLM client（支持运行时切换）。"""
        self._llm = llm_client

    # ────────────────────── 计划生成 ──────────────────────

    async def generate_plan(self, task: str) -> List[str]:
        """
        Plan-and-Execute: 将任务拆解为 3-7 个子步骤。
        失败或未启用时返回空列表。

        Chat 和 Autonomous 模式都可调用。
        """
        if not self._llm:
            return []

        try:
            from app_state import ENABLE_PLAN_AND_EXECUTE
            if not ENABLE_PLAN_AND_EXECUTE:
                return []
        except ImportError:
            return []

        prompt = (
            "请将以下任务拆解为 3-7 个可执行的子步骤，每行一个简短子目标，不要编号不要 JSON。\n"
            f"任务: {task}\n\n子步骤（每行一条）:"
        )
        try:
            import asyncio
            try:
                from core.timeout_policy import get_timeout_policy
            except ImportError:
                get_timeout_policy = None
            if get_timeout_policy is not None:
                resp = await get_timeout_policy().with_llm_timeout(
                    self._llm.chat(messages=[{"role": "user", "content": prompt}])
                )
            else:
                resp = await asyncio.wait_for(
                    self._llm.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=60.0,
                )
            content = (resp.get("content") or "").strip()
            # 去除编号前缀
            lines = [
                ln.strip().lstrip("0123456789.-) ")
                for ln in content.split("\n")
                if ln.strip()
            ][:7]
            return lines if lines else []
        except Exception as e:
            logger.debug("Plan generation failed: %s", e)
            return []

    # ────────────────────── 中途反思 ──────────────────────

    def should_reflect(
        self,
        iteration: int,
        consecutive_failures: int = 0,
        *,
        reflect_every_n: int = 5,
    ) -> bool:
        """判断当前步是否需要中途反思。"""
        if iteration == 0:
            return False
        if consecutive_failures >= 2:
            return True
        if reflect_every_n > 0 and iteration % reflect_every_n == 0:
            return True
        return False

    async def run_reflection(
        self,
        task_description: str,
        recent_steps: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        执行中途反思，返回建议文本。

        recent_steps: [{"action_type": str, "success": bool, "output_snippet": str}, ...]
        """
        if not self._llm:
            return None

        steps_text = "\n".join(
            f"[Step {i+1}] {s.get('action_type', '?')} → {'✓' if s.get('success') else '✗'} {s.get('output_snippet', '')[:100]}"
            for i, s in enumerate(recent_steps)
        )
        prompt = (
            f"任务: {task_description}\n\n"
            f"最近步骤:\n{steps_text}\n\n"
            "请用一两句话给出下一步改进建议（不要重复已失败的做法）。直接输出建议，不要 JSON。"
        )
        try:
            import asyncio
            try:
                from core.timeout_policy import get_timeout_policy
            except ImportError:
                get_timeout_policy = None
            if get_timeout_policy is not None:
                resp = await get_timeout_policy().with_llm_timeout(
                    self._llm.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=30.0,
                )
            else:
                resp = await asyncio.wait_for(
                    self._llm.chat(messages=[{"role": "user", "content": prompt}]),
                    timeout=30.0,
                )
            content = (resp.get("content") or "").strip()
            return content[:500] if content else None
        except Exception as e:
            logger.debug("Mid-loop reflection failed: %s", e)
            return None

    # ────────────────────── 策略升级 ──────────────────────

    def detect_repeated_failure(self, action_logs: list) -> int:
        """
        检测连续相似失败，返回升级等级:
        - ESCALATION_NORMAL (0): 正常
        - ESCALATION_FORCE_SWITCH (1): 强制换策略
        - ESCALATION_SKILL_FALLBACK (2): 技能降级

        action_logs: 完整的 ActionLog 列表（需有 .action.action_type, .result.success, .result.error 属性）
        """
        if not action_logs:
            return ESCALATION_NORMAL

        recent = action_logs[-5:]
        failed_logs = [log for log in recent if not log.result.success]
        if len(failed_logs) < 2:
            return ESCALATION_NORMAL

        signatures = []
        for log in failed_logs:
            sig_text = f"{log.action.action_type.value}:{log.result.error or str(log.result.output) or ''}"[:300]
            signatures.append(sig_text)

        consecutive_same = 0
        last_sig = signatures[-1]

        # 优先用 embedding 相似度
        try:
            from .vector_store import encode_text_for_similarity
            import numpy as np
            last_emb = encode_text_for_similarity(last_sig)
            if last_emb is not None:
                for i in range(len(signatures) - 1, -1, -1):
                    emb = encode_text_for_similarity(signatures[i])
                    if emb is not None and float(np.dot(last_emb, emb)) >= self._escalation_similarity_threshold:
                        consecutive_same += 1
                    else:
                        break
        except Exception:
            last_emb = None

        # 降级到 hash 对比
        if last_emb is None:
            hashes = [hashlib.md5(s.encode()).hexdigest()[:10] for s in signatures]
            last_hash = hashes[-1]
            for h in reversed(hashes):
                if h == last_hash:
                    consecutive_same += 1
                else:
                    break

        if consecutive_same >= self._escalation_skill_after_n:
            return ESCALATION_SKILL_FALLBACK
        if consecutive_same >= self._escalation_force_after_n:
            return ESCALATION_FORCE_SWITCH
        return ESCALATION_NORMAL

    # ────────────────────── 行为去重 ──────────────────────

    # 只读类型跳过去重
    DEDUP_SKIP_TYPES = frozenset(["think", "read_file", "list_directory", "get_system_info", "clipboard_read"])

    def check_action_dedup(
        self,
        action_type: str,
        params: Dict[str, Any],
        action_logs: list,
        *,
        window: int = 12,
    ) -> bool:
        """
        检查当前动作是否与最近成功步骤重复。
        返回 True 表示是重复动作。

        Duck 模式下禁用去重。
        """
        if self.is_duck_mode:
            return False
        if action_type in self.DEDUP_SKIP_TYPES:
            return False
        # call_tool screenshot 是只读
        if action_type == "call_tool":
            tool = (params or {}).get("tool_name", "")
            if tool in ("screenshot",):
                return False

        sig = self.action_signature(action_type, params)
        if not sig:
            return False

        # 只对比最近 N 条成功日志
        recent_success = [
            log for log in action_logs[-window:]
            if log.result.success
        ]
        for log in recent_success:
            old_sig = self.action_signature(
                log.action.action_type.value
                if hasattr(log.action.action_type, "value")
                else str(log.action.action_type),
                log.action.params or {},
            )
            if old_sig and old_sig == sig:
                return True
        return False

    @staticmethod
    def action_signature(action_type: str, params: Dict[str, Any]) -> Optional[str]:
        """
        生成动作指纹用于去重比较。
        """
        p = params or {}
        at = action_type
        if at == "write_file":
            return f"write_file:{p.get('path', '')}"
        if at == "create_and_run_script":
            return f"script:{p.get('name', '')}:{p.get('language', '')}"
        if at == "run_shell":
            cmd = (p.get("command") or "")[:120]
            return f"shell:{cmd}"
        if at == "open_app":
            return f"open_app:{p.get('app_name', '')}"
        if at == "close_app":
            return f"close_app:{p.get('app_name', '')}"
        if at == "call_tool":
            tool = p.get("tool_name", "")
            args = p.get("args") or {}
            key_parts = [f"call_tool:{tool}"]
            for k in ("action", "text", "content", "element_name", "query", "capsule_id"):
                v = args.get(k)
                if v:
                    key_parts.append(f"{k}={str(v)[:80]}")
            return ":".join(key_parts)
        if at == "delegate_duck":
            desc = (p.get("description") or "")[:80]
            dtype = p.get("duck_type", "")
            return f"delegate_duck:{dtype}:{desc}"
        return None

    # ────────────────────── 循环检测 ──────────────────────

    def detect_loop(self, action_type: str, params: Dict[str, Any], action_logs: list) -> bool:
        """
        检测连续 3 次相同动作指纹 → 可能死循环。
        Duck 模式下禁用。
        """
        if self.is_duck_mode:
            return False
        if len(action_logs) < 3:
            return False

        sig = self.action_signature(action_type, params)
        if not sig:
            return False

        last_sigs = []
        for log in action_logs[-3:]:
            at_val = (
                log.action.action_type.value
                if hasattr(log.action.action_type, "value")
                else str(log.action.action_type)
            )
            last_sigs.append(self.action_signature(at_val, log.action.params or {}))

        return all(s == sig for s in last_sigs)

    # ────────────────────── FINISH Guard ──────────────────────

    def should_block_finish(
        self,
        plan: List[str],
        plan_index: int,
        action_logs: list,
    ) -> Optional[str]:
        """
        检查是否应该阻止 FINISH 动作。
        返回阻止原因字符串，或 None 表示允许。
        """
        # 计划未完成
        if plan and plan_index < len(plan) - 1:
            remaining = plan[plan_index + 1:]
            return f"计划还有 {len(remaining)} 步未完成: {remaining}。请继续执行，不要提前结束。"

        # 有失败的 duck 委派（排除被 dedup 拦截的和 finish_blocked 的）
        failed_ducks = [
            log for log in action_logs
            if (
                (hasattr(log.action.action_type, "value") and log.action.action_type.value == "delegate_duck")
                or str(log.action.action_type) == "delegate_duck"
            ) and not log.result.success
            and log.result.error not in ("duplicate_action_blocked", "finish_blocked")
        ]
        if failed_ducks:
            return f"有 {len(failed_ducks)} 个 delegate_duck 子任务失败。请重新 delegate_duck 委派此子任务，不要直接结束。"

        return None
