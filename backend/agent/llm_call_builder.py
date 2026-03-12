"""
LLMCallBuilder — 统一 LLM 调用基础设施

Chat 模式 (core.py) 与 Autonomous 模式 (autonomous_agent.py) 共享:
- CoT / Extended Thinking 注入
- Token 预算管理（按任务 tier / 步数动态调整）
- 模型限速与请求延迟
- 截断检测 (finish_reason=length / completion_tokens 达上限)
"""

import asyncio
import copy
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 模型级 max_tokens 上限（避免超出模型限制导致 400 错误）──
_MODEL_MAX_TOKENS: Dict[str, int] = {
    "deepseek-chat": 8192,
    "deepseek-reasoner": 8000,
    "deepseek-coder": 8192,
}

# ── 请求间延迟（秒），可通过环境变量覆盖 ──
def _get_request_delay() -> float:
    d = float(os.environ.get("LLM_REQUEST_DELAY_SECONDS", "2.0"))
    return max(d, 0)


class LLMCallBuilder:
    """
    统一封装 LLM 调用的前置处理与后置处理。
    不持有 LLM client — 由调用方注入。
    """

    def __init__(self, llm_client, *, is_local_model: bool = False):
        self.llm = llm_client
        self.is_local = is_local_model
        self._provider = (llm_client.config.provider or "").lower()
        self._model = (llm_client.config.model or "").lower()

    # ────────────────────── CoT / Extended Thinking ──────────────────────

    def inject_cot(
        self,
        messages: List[Dict[str, Any]],
        *,
        enable_extended_thinking: bool = False,
        thinking_budget_tokens: int = 8000,
    ) -> tuple:
        """
        注入 Chain-of-Thought 或 Extended Thinking。

        Returns:
            (messages, extra_body)
            - messages: 可能含 CoT 前缀的消息列表（浅拷贝，不改原始）
            - extra_body: 传给 llm.chat() 的 extra_body（如 Anthropic thinking）
        """
        extra_body: Optional[Dict[str, Any]] = None

        if not enable_extended_thinking:
            return messages, extra_body

        if self._provider == "anthropic":
            budget = max(1024, int(thinking_budget_tokens))
            extra_body = {"thinking": {"type": "enabled", "budget_tokens": budget}}
            logger.info("Extended Thinking enabled: provider=anthropic budget=%d", budget)
        else:
            cot_prefix = (
                "[Chain-of-Thought Reasoning] 在输出最终 JSON 动作之前，"
                "请先在 <thinking>...</thinking> 标签内逐步推理分析当前状态、"
                "潜在风险和最优下一步，然后再输出 JSON。"
            )
            if messages and messages[0].get("role") == "system":
                messages = copy.copy(messages)
                messages[0] = dict(messages[0])
                messages[0]["content"] = cot_prefix + "\n\n" + messages[0]["content"]
            logger.info("CoT prompt injection enabled: provider=%s", self._provider)

        return messages, extra_body

    # ────────────────────── Token 预算 ──────────────────────

    def compute_max_tokens(
        self,
        *,
        tier: str = "complex",
        step_count: int = 0,
        config_max: int = 0,
    ) -> int:
        """
        根据任务 tier 和步数计算 max_tokens。

        Chat 模式通过 tier ("simple"/"complex") 控制；
        Autonomous 模式通过 step_count 动态调整。
        """
        # Autonomous 步数方案
        if step_count >= 8:
            base = 16384
        elif step_count >= 5:
            base = 12288
        elif step_count >= 1:
            base = 8192
        else:
            # Chat tier 方案
            if tier == "simple":
                base = 4096
            else:
                base = 8192  # 首步也用 8192

        # 用户配置兜底
        if config_max > 0:
            base = max(base, config_max)

        # 模型级上限裁剪
        for model_key, model_limit in _MODEL_MAX_TOKENS.items():
            if model_key in self._model:
                if base > model_limit:
                    logger.info("Capping max_tokens from %d to %d for model %s", base, model_limit, self._model)
                    base = model_limit
                break

        return base

    # ────────────────────── 截断检测 ──────────────────────

    @staticmethod
    def is_truncated(
        finish_reason: str,
        completion_tokens: int = 0,
        effective_max_tokens: int = 4096,
    ) -> bool:
        """
        统一截断检测逻辑。

        部分 API 网关不正确上报 finish_reason=length，
        补充检测 completion_tokens 达到 max_tokens 上限。
        """
        if finish_reason == "length":
            return True
        if completion_tokens > 0 and completion_tokens >= effective_max_tokens - 10:
            return True
        return False

    # ────────────────────── 请求延迟 ──────────────────────

    async def pre_request_delay(self, iteration: int) -> None:
        """非首轮、非本地模型时等待，避免网关限流。"""
        if iteration > 0 and not self.is_local:
            delay = _get_request_delay()
            if delay > 0:
                await asyncio.sleep(delay)
