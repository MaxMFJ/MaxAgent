"""
Agent 中间件框架 — 借鉴 DeerFlow 2.0 中间件链模式

每个中间件在 Agent 主循环的特定阶段执行，实现横切关注点解耦。
中间件按注册顺序执行，支持 before_iteration / after_action / on_finish 三个钩子。

用法:
    chain = MiddlewareChain()
    chain.add(ContextSummarizationMiddleware(...))
    chain.add(ActionDeduplicationMiddleware(...))
    chain.add(PlanTrackingMiddleware(...))
    chain.add(DuckDelegationMiddleware(...))

    # 在 run_autonomous 主循环中:
    async for event in chain.before_iteration(context):
        yield event

    # 动作执行后:
    result = chain.after_action(action, result, context)

    # FINISH 前:
    block_reason = chain.check_finish(action, context)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .action_schema import AgentAction, ActionResult, TaskContext

logger = logging.getLogger(__name__)


class AgentMiddleware(ABC):
    """Agent 中间件基类"""

    name: str = "base"
    enabled: bool = True

    async def before_iteration(
        self,
        context: "TaskContext",
        iteration: int,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """每次迭代开始前执行。可 yield 事件给前端。"""
        return
        yield  # make this an async generator

    async def after_action(
        self,
        action: "AgentAction",
        result: "ActionResult",
        context: "TaskContext",
    ) -> Optional["ActionResult"]:
        """动作执行后处理。可修改 result 或返回 None 不干预。"""
        return None

    def check_finish(
        self,
        action: "AgentAction",
        context: "TaskContext",
    ) -> Optional[str]:
        """FINISH 动作前检查。返回阻止原因或 None 允许。"""
        return None

    def inject_hint(self, context: "TaskContext") -> Optional[str]:
        """向下一轮 LLM 提示注入额外信息。返回字符串或 None。"""
        return None


class MiddlewareChain:
    """中间件链管理器"""

    def __init__(self):
        self._middlewares: List[AgentMiddleware] = []

    def add(self, middleware: AgentMiddleware) -> "MiddlewareChain":
        """添加中间件（按添加顺序执行）"""
        self._middlewares.append(middleware)
        logger.debug(f"Middleware added: {middleware.name}")
        return self

    @property
    def middlewares(self) -> List[AgentMiddleware]:
        return [m for m in self._middlewares if m.enabled]

    async def before_iteration(
        self,
        context: "TaskContext",
        iteration: int,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行所有中间件的 before_iteration"""
        for mw in self.middlewares:
            try:
                async for event in mw.before_iteration(context, iteration):
                    yield event
            except Exception as e:
                logger.warning(f"Middleware {mw.name}.before_iteration error: {e}")

    async def after_action(
        self,
        action: "AgentAction",
        result: "ActionResult",
        context: "TaskContext",
    ) -> "ActionResult":
        """执行所有中间件的 after_action（链式处理）"""
        current_result = result
        for mw in self.middlewares:
            try:
                modified = await mw.after_action(action, current_result, context)
                if modified is not None:
                    current_result = modified
            except Exception as e:
                logger.warning(f"Middleware {mw.name}.after_action error: {e}")
        return current_result

    def check_finish(
        self,
        action: "AgentAction",
        context: "TaskContext",
    ) -> Optional[str]:
        """依次检查各中间件是否阻止 FINISH，返回第一个阻止原因"""
        for mw in self.middlewares:
            try:
                reason = mw.check_finish(action, context)
                if reason:
                    return reason
            except Exception as e:
                logger.warning(f"Middleware {mw.name}.check_finish error: {e}")
        return None

    def collect_hints(self, context: "TaskContext") -> str:
        """收集所有中间件的提示信息"""
        hints = []
        for mw in self.middlewares:
            try:
                hint = mw.inject_hint(context)
                if hint:
                    hints.append(hint)
            except Exception as e:
                logger.warning(f"Middleware {mw.name}.inject_hint error: {e}")
        return "\n".join(hints) if hints else ""
