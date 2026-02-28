"""
Strategy Router
Input: UpgradePlan
Output: ImplementationStrategy
Heuristics can override planner strategy.
"""

import logging
from typing import Optional, Set

from .models import UpgradePlan, ImplementationStrategy

logger = logging.getLogger(__name__)

CURSOR_CLI_INDICATORS = [
    "daemon", "monitoring", "restart", "background", "service",
    "守护进程", "监控", "后台", "服务",
]
MULTI_FILE_INDICATORS = ["multiple files", "integration", "多文件", "集成", "整合"]


def route_strategy(plan: UpgradePlan, existing_tool_names: Optional[Set[str]] = None) -> ImplementationStrategy:
    """
    Route upgrade plan to implementation strategy.
    Planner strategy can be overridden by heuristics.
    """
    existing_tool_names = existing_tool_names or set()
    plan_lower = (plan.plan + " " + plan.goal + " " + plan.reason).lower()

    # If tool already exists
    for name in existing_tool_names:
        if name.lower() in plan_lower:
            logger.info(f"[Upgrade] Strategy: EXISTING_TOOLS (found {name})")
            return ImplementationStrategy.EXISTING_TOOLS

    # CURSOR_CLI: daemon, monitoring, restart, background, service
    for kw in CURSOR_CLI_INDICATORS:
        if kw in plan_lower:
            logger.info(f"[Upgrade] Strategy: CURSOR_CLI (keyword: {kw})")
            return ImplementationStrategy.CURSOR_CLI

    # CURSOR_CLI: multiple files or integration
    for kw in MULTI_FILE_INDICATORS:
        if kw in plan_lower:
            logger.info(f"[Upgrade] Strategy: CURSOR_CLI (multi-file: {kw})")
            return ImplementationStrategy.CURSOR_CLI

    # Multiple target files
    if len(plan.target_files) > 1:
        logger.info("[Upgrade] Strategy: CURSOR_CLI (multiple target files)")
        return ImplementationStrategy.CURSOR_CLI

    # Simple logic, single file → LLM_SCRIPT
    if len(plan.target_files) == 1:
        logger.info("[Upgrade] Strategy: LLM_SCRIPT (single file)")
        return ImplementationStrategy.LLM_SCRIPT

    # Default: use planner's choice
    return plan.strategy
