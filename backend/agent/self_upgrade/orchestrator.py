"""
SelfUpgradeOrchestrator
Planner → Strategy Router → Executor → Validation → Activation
Deterministic stages, block until result known.
Fallback: CURSOR_CLI → CURSOR_GUI → LLM_SCRIPT
"""

import asyncio
import logging
from typing import AsyncGenerator, Callable, Dict, Optional, Set

from .models import (
    ImplementationStrategy,
    UpgradePlan,
    UpgradeStage,
    UpgradeTask,
)
from .planner import plan_upgrade
from .strategy_router import route_strategy
from .executors import execute_llm_script, execute_cursor_cli, execute_cursor_gui
from .validator import validate
from .activation import activate, set_load_generated_tools

logger = logging.getLogger(__name__)

FALLBACK_ORDER = [
    ImplementationStrategy.CURSOR_CLI,
    ImplementationStrategy.CURSOR_GUI,
    ImplementationStrategy.LLM_SCRIPT,
]


class SelfUpgradeOrchestrator:
    """
    Deterministic self-upgrade orchestration.
    Every stage blocks until result known.
    """

    def __init__(
        self,
        llm_chat,
        on_load_generated_tools: Optional[Callable[[], list]] = None,
        get_existing_tools: Optional[Callable[[], Set[str]]] = None,
    ):
        self.llm_chat = llm_chat
        self._on_load = on_load_generated_tools
        self._get_existing = get_existing_tools or (lambda: set())
        if on_load_generated_tools:
            set_load_generated_tools(on_load_generated_tools)
        self._upgrading = False

    def _update_task_stage(self, task: UpgradeTask, stage: UpgradeStage) -> None:
        task.stage = stage
        import time
        task.updated_at = time.time()

    async def run(self, goal: str) -> AsyncGenerator[Dict, None]:
        """
        Execute full upgrade flow.
        Blocks at each stage until result known.
        """
        if self._upgrading:
            logger.warning("[Upgrade] Already upgrading, skip")
            yield {"type": "upgrade_error", "error": "已有升级任务在执行中"}
            return

        self._upgrading = True
        task: Optional[UpgradeTask] = None

        try:
            # 1) Plan
            logger.info(f"[Upgrade] Planned: {goal}")
            plan = await plan_upgrade(goal, self.llm_chat)
            if not plan:
                logger.error("[Upgrade] Planning failed")
                yield {"type": "upgrade_error", "error": "无法生成升级方案"}
                return

            task = UpgradeTask.create(plan)
            self._update_task_stage(task, UpgradeStage.PLANNED)
            yield {"type": "upgrade_progress", "phase": "planned", "plan": plan.plan}

            # 2) Strategy
            existing = self._get_existing()
            strategy = route_strategy(plan, existing)
            self._update_task_stage(task, UpgradeStage.STRATEGY_SELECTED)
            logger.info(f"[Upgrade] Strategy: {strategy.value}")
            yield {"type": "upgrade_progress", "phase": "strategy", "strategy": strategy.value}

            def _stage_cb(s: UpgradeStage):
                if task:
                    self._update_task_stage(task, s)

            # 3) Execute
            success = False
            err_msg = ""

            if strategy == ImplementationStrategy.EXISTING_TOOLS:
                # No file creation - skip validation/activation
                logger.info("[Upgrade] EXISTING_TOOLS: no execution needed")
                self._update_task_stage(task, UpgradeStage.DONE)
                yield {
                    "type": "upgrade_complete",
                    "plan": plan.plan,
                    "loaded_tools": [],
                }
                return
            else:
                strategies_to_try = [strategy] + [s for s in FALLBACK_ORDER if s != strategy]
                for s in strategies_to_try:
                    if s == ImplementationStrategy.LLM_SCRIPT:
                        success, err_msg = await execute_llm_script(plan, self.llm_chat, _stage_cb)
                    elif s == ImplementationStrategy.CURSOR_CLI:
                        success, err_msg = await execute_cursor_cli(plan, _stage_cb)
                    elif s == ImplementationStrategy.CURSOR_GUI:
                        success, err_msg = await execute_cursor_gui(plan, _stage_cb)
                    else:
                        continue

                    if success:
                        if s != strategy:
                            logger.info(f"[Upgrade] Fallback to {s.value}")
                        break
                    else:
                        logger.warning(f"[Upgrade] {s.value} failed: {err_msg}")

            if not success:
                self._update_task_stage(task, UpgradeStage.FAILED)
                yield {"type": "upgrade_error", "error": err_msg or "执行失败"}
                return

            # 4) Validate
            self._update_task_stage(task, UpgradeStage.VALIDATING)
            logger.info("[Upgrade] Validation...")
            valid, val_err = validate(plan)
            if not valid:
                self._update_task_stage(task, UpgradeStage.FAILED)
                yield {"type": "upgrade_error", "error": val_err or "校验失败"}
                return
            logger.info("[Upgrade] Validation passed")

            # 5) Activate
            self._update_task_stage(task, UpgradeStage.ACTIVATING)
            loaded = activate()
            logger.info("[Upgrade] Activated")
            self._update_task_stage(task, UpgradeStage.DONE)

            yield {
                "type": "upgrade_complete",
                "plan": plan.plan,
                "loaded_tools": loaded,
            }

        except Exception as e:
            logger.exception(f"[Upgrade] Orchestrator error: {e}")
            if task:
                self._update_task_stage(task, UpgradeStage.FAILED)
            yield {"type": "upgrade_error", "error": str(e)}
        finally:
            self._upgrading = False


_orchestrator: Optional[SelfUpgradeOrchestrator] = None


def get_orchestrator(
    llm_chat=None,
    on_load_generated_tools=None,
    get_existing_tools=None,
) -> Optional[SelfUpgradeOrchestrator]:
    global _orchestrator
    if _orchestrator is None and llm_chat:
        _orchestrator = SelfUpgradeOrchestrator(
            llm_chat=llm_chat,
            on_load_generated_tools=on_load_generated_tools,
            get_existing_tools=get_existing_tools,
        )
    return _orchestrator


async def upgrade(goal: str) -> AsyncGenerator[Dict, None]:
    """
    Main entry: upgrade(goal)
    Requires orchestrator to be initialized via get_orchestrator().
    """
    orch = get_orchestrator()
    if not orch:
        yield {"type": "upgrade_error", "error": "SelfUpgradeOrchestrator 未初始化"}
        return
    async for ev in orch.run(goal):
        yield ev
