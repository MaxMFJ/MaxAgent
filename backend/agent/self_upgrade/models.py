"""
Self-Upgrade Data Models
"""

from dataclasses import dataclass, field
from enum import Enum
import time
import uuid


class ImplementationStrategy(str, Enum):
    EXISTING_TOOLS = "EXISTING_TOOLS"
    LLM_SCRIPT = "LLM_SCRIPT"


class UpgradeStage(str, Enum):
    PLANNED = "PLANNED"
    STRATEGY_SELECTED = "STRATEGY_SELECTED"
    EXECUTING_LLM = "EXECUTING_LLM"
    VALIDATING = "VALIDATING"
    ACTIVATING = "ACTIVATING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class UpgradePlan:
    goal: str
    plan: str
    target_files: list
    strategy: ImplementationStrategy
    reason: str

    @classmethod
    def from_dict(cls, d: dict) -> "UpgradePlan":
        s = d.get("strategy", "LLM_SCRIPT").upper().replace("-", "_")
        strategy = ImplementationStrategy.EXISTING_TOOLS
        for st in ImplementationStrategy:
            if st.value == s:
                strategy = st
                break
        return cls(
            goal=d.get("goal", ""),
            plan=d.get("plan", ""),
            target_files=list(d.get("target_files", [])),
            strategy=strategy,
            reason=d.get("reason", ""),
        )


@dataclass
class UpgradeTask:
    id: str
    plan: UpgradePlan
    stage: UpgradeStage
    results: dict
    created_at: float
    updated_at: float

    @classmethod
    def create(cls, plan: UpgradePlan) -> "UpgradeTask":
        now = time.time()
        return cls(
            id=str(uuid.uuid4())[:8],
            plan=plan,
            stage=UpgradeStage.PLANNED,
            results={},
            created_at=now,
            updated_at=now,
        )
