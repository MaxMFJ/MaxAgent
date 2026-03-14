"""
Strategy Router
Input: UpgradePlan
Output: ImplementationStrategy
Route to LLM_SCRIPT or EXISTING_TOOLS.
"""

import logging
from typing import Optional, Set

from .models import UpgradePlan, ImplementationStrategy

logger = logging.getLogger(__name__)


def route_strategy(plan: UpgradePlan, existing_tool_names: Optional[Set[str]] = None) -> ImplementationStrategy:
    """
    Route upgrade plan to implementation strategy.
    Only LLM_SCRIPT and EXISTING_TOOLS are supported.
    """
    existing_tool_names = existing_tool_names or set()
    plan_lower = (plan.plan + " " + plan.goal + " " + plan.reason).lower()

    # If tool already exists
    for name in existing_tool_names:
        if name.lower() in plan_lower:
            logger.info(f"[Upgrade] Strategy: EXISTING_TOOLS (found {name})")
            return ImplementationStrategy.EXISTING_TOOLS

    # Default: LLM generates code
    logger.info("[Upgrade] Strategy: LLM_SCRIPT")
    return ImplementationStrategy.LLM_SCRIPT
