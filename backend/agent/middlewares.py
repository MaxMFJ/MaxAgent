"""
内置中间件实现 — 从 run_autonomous() 中提取的横切关注点

1. ContextSummarizationMiddleware - token 接近上限时自动摘要
2. ActionDeduplicationMiddleware  - 去重 + 循环检测
3. PlanTrackingMiddleware         - 计划跟踪 + FINISH 守卫
4. DuckDelegationMiddleware       - 异步子代理管理 + 并发限制
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from .middleware import AgentMiddleware

if TYPE_CHECKING:
    from .action_schema import AgentAction, ActionResult, TaskContext

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. Context Summarization Middleware
# ═══════════════════════════════════════════════════════════════════

class ContextSummarizationMiddleware(AgentMiddleware):
    """
    在 token 接近上限时自动压缩对话上下文。
    借鉴 DeerFlow SummarizationMiddleware: 保留最近消息，摘要旧消息。

    触发条件:
    - action_logs 条目数超过 trigger_threshold
    - 预估 token 数超过 token_budget 的 ratio
    """

    name = "context_summarization"

    def __init__(
        self,
        token_budget: int = 80000,
        trigger_ratio: float = 0.7,
        trigger_threshold: int = 20,
        keep_recent: int = 8,
    ):
        self.token_budget = token_budget
        self.trigger_ratio = trigger_ratio
        self.trigger_threshold = trigger_threshold
        self.keep_recent = keep_recent
        self._last_compression_at: int = 0

    async def before_iteration(
        self, context: "TaskContext", iteration: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """检查是否需要压缩上下文"""
        log_count = len(context.action_logs)

        # 至少间隔 5 步才触发二次压缩
        if log_count - self._last_compression_at < 5:
            return

        if log_count < self.trigger_threshold:
            return

        # 估算当前上下文 token 消耗
        est_tokens = self._estimate_context_tokens(context)
        threshold = int(self.token_budget * self.trigger_ratio)

        if est_tokens < threshold:
            return

        # 执行压缩
        logger.info(
            "Context summarization triggered: %d logs, ~%d tokens (threshold=%d)",
            log_count, est_tokens, threshold,
        )

        compressed_count = self._compress_action_logs(context)
        self._last_compression_at = len(context.action_logs)

        yield {
            "type": "context_summarized",
            "original_logs": log_count,
            "compressed_count": compressed_count,
            "estimated_tokens": est_tokens,
            "iteration": iteration,
        }

    def _estimate_context_tokens(self, context: "TaskContext") -> int:
        """粗略估算 action_logs 的 token 占用（~4 chars = 1 token）"""
        total_chars = 0
        for log in context.action_logs:
            total_chars += len(str(log.action.params or ""))
            total_chars += len(str(log.result.output or ""))
            total_chars += len(str(log.result.error or ""))
            total_chars += len(log.action.reasoning or "")
        return total_chars // 4

    def _compress_action_logs(self, context: "TaskContext") -> int:
        """压缩旧的 action logs，保留最近的和关键节点"""
        logs = context.action_logs
        if len(logs) <= self.keep_recent:
            return 0

        old_logs = logs[:-self.keep_recent]
        recent_logs = logs[-self.keep_recent:]

        # 对旧 logs 进行摘要：保留 action_type 和 success，清除大输出
        compressed = 0
        for log in old_logs:
            if log.result.output and len(str(log.result.output)) > 200:
                output_str = str(log.result.output)
                log.result.output = output_str[:100] + f"...[compressed, was {len(output_str)} chars]"
                compressed += 1
            if log.action.reasoning and len(log.action.reasoning) > 100:
                log.action.reasoning = log.action.reasoning[:80] + "..."
                compressed += 1

        return compressed


# ═══════════════════════════════════════════════════════════════════
# 2. Action Deduplication Middleware
# ═══════════════════════════════════════════════════════════════════

class ActionDeduplicationMiddleware(AgentMiddleware):
    """
    检测并阻止重复动作和循环模式。
    - 完全相同的成功动作不会再次执行
    - 连续 3 次相同 action_type 触发循环告警
    """

    name = "action_dedup"

    # 不做去重检查的 action 类型（每次执行结果可能不同）
    SKIP_TYPES = {"read_file", "think", "call_tool", "get_system_info"}

    def __init__(self, window: int = 12):
        self.window = window
        self._loop_hint: Optional[str] = None

    async def before_iteration(
        self, context: "TaskContext", iteration: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """检测循环模式"""
        logs = context.action_logs
        if len(logs) < 3:
            return

        # 检测连续 3 次相同 action_type
        last3_types = [
            (log.action.action_type.value if hasattr(log.action.action_type, 'value')
             else str(log.action.action_type))
            for log in logs[-3:]
        ]
        if len(set(last3_types)) == 1 and last3_types[0] not in self.SKIP_TYPES:
            self._loop_hint = (
                f"⚠️ 你已经连续 3 次执行相同操作（{last3_types[0]}），"
                f"这是一个无效循环。请立即改用不同的策略或执行下一步。"
            )
            yield {
                "type": "loop_detected",
                "action_type": last3_types[0],
                "iteration": iteration,
            }

    def inject_hint(self, context: "TaskContext") -> Optional[str]:
        """注入循环检测提示"""
        hint = self._loop_hint
        self._loop_hint = None
        return hint

    def is_duplicate(self, action: "AgentAction", context: "TaskContext") -> bool:
        """检查 action 是否与最近成功的动作重复"""
        at = action.action_type.value if hasattr(action.action_type, 'value') else str(action.action_type)
        if at in self.SKIP_TYPES:
            return False

        sig = self._action_signature(at, action.params or {})
        for log in context.action_logs[-self.window:]:
            if not log.result.success:
                continue
            old_at = log.action.action_type.value if hasattr(log.action.action_type, 'value') else str(log.action.action_type)
            old_sig = self._action_signature(old_at, log.action.params or {})
            if sig == old_sig:
                return True
        return False

    @staticmethod
    def _action_signature(action_type: str, params: dict) -> str:
        """生成动作签名用于去重比较"""
        import json
        try:
            return f"{action_type}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
        except (TypeError, ValueError):
            return f"{action_type}:{str(params)}"


# ═══════════════════════════════════════════════════════════════════
# 3. Plan Tracking Middleware
# ═══════════════════════════════════════════════════════════════════

class PlanTrackingMiddleware(AgentMiddleware):
    """
    跟踪 Plan-and-Execute 计划进度，阻止计划未完成时的 FINISH。
    当步骤完成时自动推进 plan_index。
    """

    name = "plan_tracking"

    def __init__(self):
        self._plan: List[str] = []
        self._plan_index: int = 0
        self._finish_block_hint: Optional[str] = None

    def set_plan(self, plan: List[str]):
        """设置执行计划"""
        self._plan = plan
        self._plan_index = 0

    @property
    def current_step(self) -> Optional[str]:
        if self._plan and self._plan_index < len(self._plan):
            return self._plan[self._plan_index]
        return None

    @property
    def remaining_steps(self) -> List[str]:
        if self._plan and self._plan_index < len(self._plan) - 1:
            return self._plan[self._plan_index + 1:]
        return []

    def advance(self):
        """推进到下一步"""
        if self._plan and self._plan_index < len(self._plan) - 1:
            self._plan_index += 1
            logger.info(f"Plan advanced to step {self._plan_index + 1}/{len(self._plan)}: {self.current_step}")

    def check_finish(
        self, action: "AgentAction", context: "TaskContext"
    ) -> Optional[str]:
        """计划未完成时阻止 FINISH"""
        remaining = self.remaining_steps
        if remaining:
            next_step = remaining[0]
            reason = (
                f"计划还有 {len(remaining)} 步未完成。"
                f"请继续执行下一步：「{next_step}」。"
                f"禁止在计划未完成时结束任务。"
            )
            self._finish_block_hint = reason
            return reason
        return None

    def inject_hint(self, context: "TaskContext") -> Optional[str]:
        hint = self._finish_block_hint
        self._finish_block_hint = None
        return hint


# ═══════════════════════════════════════════════════════════════════
# 4. Duck Delegation Middleware
# ═══════════════════════════════════════════════════════════════════

class DuckDelegationMiddleware(AgentMiddleware):
    """
    管理异步 Duck 子代理生命周期。
    - 限制最大并发 Duck 数
    - 收集异步完成的 Duck 结果
    - 阻止有 pending Ducks 时的 FINISH
    """

    name = "duck_delegation"

    MAX_CONCURRENT_DUCKS = 3  # 最大并发 Duck 数（对齐 DeerFlow 的 3）

    def __init__(self):
        self._pending_futures: Dict[str, Any] = {}  # task_id -> future
        self._pending_descriptions: Dict[str, str] = {}  # task_id -> desc
        self._collected_results: List[Dict[str, Any]] = []
        self._result_hint: Optional[str] = None

    @property
    def pending_count(self) -> int:
        return len(self._pending_futures)

    def can_dispatch(self) -> bool:
        """是否还能派发更多 Duck"""
        return self.pending_count < self.MAX_CONCURRENT_DUCKS

    def register_dispatch(self, task_id: str, future: Any, description: str):
        """注册已派发的 Duck 任务"""
        self._pending_futures[task_id] = future
        self._pending_descriptions[task_id] = description[:100]

    async def before_iteration(
        self, context: "TaskContext", iteration: int
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """收集已完成的 Duck 结果"""
        if not self._pending_futures:
            return

        completed_ids = [
            tid for tid, fut in self._pending_futures.items() if fut.done()
        ]

        for task_id in completed_ids:
            future = self._pending_futures.pop(task_id)
            desc = self._pending_descriptions.pop(task_id, "")

            try:
                completed_task = future.result()
                from services.duck_protocol import TaskStatus
                success = completed_task.status == TaskStatus.COMPLETED
                result_info = {
                    "task_id": task_id,
                    "success": success,
                    "description": desc,
                    "output": completed_task.output,
                    "error": completed_task.error,
                    "duck_id": completed_task.assigned_duck_id,
                }
                self._collected_results.append(result_info)

                # 构建提示
                status = "✅ 成功" if success else "❌ 失败"
                hint = f"【Duck 子任务完成】{status}：{desc}"
                if completed_task.output:
                    hint += f"\n结果：{str(completed_task.output)[:300]}"
                if completed_task.error:
                    hint += f"\n错误：{completed_task.error[:200]}"
                self._result_hint = (self._result_hint or "") + f"\n{hint}"

                yield {
                    "type": "duck_result_collected",
                    "task_id": task_id,
                    "duck_id": result_info["duck_id"],
                    "success": success,
                    "description": desc,
                    "pending_count": self.pending_count,
                }
            except Exception as e:
                logger.warning(f"Failed to collect duck result for {task_id}: {e}")

    def check_finish(
        self, action: "AgentAction", context: "TaskContext"
    ) -> Optional[str]:
        """有 pending Ducks 时阻止 FINISH"""
        if self._pending_futures:
            descs = list(self._pending_descriptions.values())
            return (
                f"还有 {len(self._pending_futures)} 个 Duck 子任务正在执行中："
                f"{', '.join(descs)}。请等待它们完成后再结束任务。"
            )
        return None

    def inject_hint(self, context: "TaskContext") -> Optional[str]:
        """注入 Duck 结果提示"""
        hint = self._result_hint
        self._result_hint = None
        return hint
