"""
EvoMap GEP Protocol Data Models
Defines Gene, Capsule, EvolutionEvent, and Node registration schemas
conforming to the Genome Evolution Protocol (GEP) specification.
"""

import hashlib
import json
import platform
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class GeneCategory(str, Enum):
    REPAIR = "repair"
    OPTIMIZE = "optimize"
    INNOVATE = "innovate"
    CAPABILITY = "capability"


class CapsuleOutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class NodeStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    SYNCING = "syncing"


GEP_SCHEMA_VERSION = "1.5.0"


@dataclass
class Gene:
    """A reusable evolution strategy unit in GEP."""
    id: str
    category: GeneCategory
    signals_match: List[str]
    preconditions: List[str]
    strategy: List[str]
    constraints: Dict[str, Any] = field(default_factory=lambda: {"max_files": 20, "forbidden_paths": [".git"]})
    validation: List[str] = field(default_factory=list)
    type: str = "Gene"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value if isinstance(self.category, GeneCategory) else self.category
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Gene":
        cat = data.get("category", "capability")
        if isinstance(cat, str):
            try:
                cat = GeneCategory(cat)
            except ValueError:
                cat = GeneCategory.CAPABILITY
        return cls(
            id=data["id"],
            category=cat,
            signals_match=data.get("signals_match", []),
            preconditions=data.get("preconditions", []),
            strategy=data.get("strategy", []),
            constraints=data.get("constraints", {}),
            validation=data.get("validation", []),
            type=data.get("type", "Gene"),
        )


def compute_asset_id(obj: Dict[str, Any]) -> str:
    """Compute deterministic SHA-256 asset_id for a Gene or Capsule."""
    exclude_keys = {"asset_id", "env_fingerprint", "a2a"}
    filtered = {k: v for k, v in sorted(obj.items()) if k not in exclude_keys}
    raw = json.dumps(filtered, sort_keys=True, ensure_ascii=False)
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def get_env_fingerprint() -> Dict[str, Any]:
    """Capture current environment fingerprint."""
    return {
        "python_version": platform.python_version(),
        "platform": platform.system().lower(),
        "arch": platform.machine(),
        "os_release": platform.release(),
        "macagent_version": "1.0.0",
        "captured_at": datetime.utcnow().isoformat() + "Z",
    }


@dataclass
class CapsuleOutcome:
    status: CapsuleOutcomeStatus
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status.value, "score": self.score}


@dataclass
class Capsule:
    """A solidified, validated evolution result in GEP."""
    id: str
    trigger: List[str]
    gene: str
    summary: str
    confidence: float = 0.85
    blast_radius: Dict[str, int] = field(default_factory=lambda: {"files": 0, "lines": 0})
    outcome: Optional[CapsuleOutcome] = None
    success_streak: int = 0
    env_fingerprint: Dict[str, Any] = field(default_factory=get_env_fingerprint)
    a2a: Dict[str, Any] = field(default_factory=lambda: {"eligible_to_broadcast": True})
    asset_id: str = ""
    schema_version: str = GEP_SCHEMA_VERSION
    type: str = "Capsule"

    def __post_init__(self):
        if not self.asset_id:
            self.asset_id = compute_asset_id(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.outcome:
            d["outcome"] = self.outcome.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capsule":
        outcome_data = data.get("outcome")
        outcome = None
        if outcome_data:
            status = outcome_data.get("status", "success")
            try:
                status = CapsuleOutcomeStatus(status)
            except ValueError:
                status = CapsuleOutcomeStatus.SUCCESS
            outcome = CapsuleOutcome(status=status, score=outcome_data.get("score", 0.0))
        return cls(
            id=data.get("id", f"capsule_{int(time.time() * 1000)}"),
            trigger=data.get("trigger", []),
            gene=data.get("gene", ""),
            summary=data.get("summary", ""),
            confidence=data.get("confidence", 0.85),
            blast_radius=data.get("blast_radius", {}),
            outcome=outcome,
            success_streak=data.get("success_streak", 0),
            env_fingerprint=data.get("env_fingerprint", get_env_fingerprint()),
            a2a=data.get("a2a", {"eligible_to_broadcast": True}),
            asset_id=data.get("asset_id", ""),
            schema_version=data.get("schema_version", GEP_SCHEMA_VERSION),
        )


@dataclass
class EvolutionEvent:
    """An auditable record of an evolution action."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    gene_id: str = ""
    capsule_id: str = ""
    intent: str = ""  # repair / optimize / innovate / inherit / publish
    signals: List[str] = field(default_factory=list)
    summary: str = ""
    outcome: str = "pending"  # pending / success / failure
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class NodeRegistration:
    """Registration payload for an EvoMap network node."""
    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_name: str = "Chow Duck"
    agent_version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    platform: str = field(default_factory=lambda: platform.system().lower())
    arch: str = field(default_factory=lambda: platform.machine())
    gep_version: str = GEP_SCHEMA_VERSION
    endpoint: str = ""
    status: NodeStatus = NodeStatus.ONLINE
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, NodeStatus) else self.status
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NodeRegistration":
        status = data.get("status", "online")
        try:
            status = NodeStatus(status)
        except ValueError:
            status = NodeStatus.ONLINE
        return cls(
            node_id=data.get("node_id", str(uuid.uuid4())),
            agent_name=data.get("agent_name", "Chow Duck"),
            agent_version=data.get("agent_version", "1.0.0"),
            capabilities=data.get("capabilities", []),
            platform=data.get("platform", ""),
            arch=data.get("arch", ""),
            gep_version=data.get("gep_version", GEP_SCHEMA_VERSION),
            endpoint=data.get("endpoint", ""),
            status=status,
            registered_at=data.get("registered_at", ""),
            metadata=data.get("metadata", {}),
        )
