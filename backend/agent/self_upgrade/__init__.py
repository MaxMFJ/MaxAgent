"""
Self-Upgrade Orchestration Framework
Deterministic: Planner → Strategy Router → Executor → Validation → Activation
"""

from .models import (
    ImplementationStrategy,
    UpgradeStage,
    UpgradePlan,
    UpgradeTask,
)
from .orchestrator import SelfUpgradeOrchestrator, upgrade, get_orchestrator

__all__ = [
    "ImplementationStrategy",
    "UpgradeStage",
    "UpgradePlan",
    "UpgradeTask",
    "SelfUpgradeOrchestrator",
    "upgrade",
    "get_orchestrator",
]
