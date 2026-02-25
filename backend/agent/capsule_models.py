"""
EvoMap Skill Capsule 数据模型（本地可执行）
与 GEP Capsule/Gene 兼容：支持 gene/capsule/metadata/signature 等字段，
同时支持可执行 skill 规范：id, description, inputs, outputs, procedure/steps。
支持 GEP ↔ Skill 双向转换、版本兼容、priority/retry/condition 等执行控制字段。
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import time

CAPSULE_SKILL_SCHEMA_VERSION = "1.1.0"
COMPATIBLE_SCHEMA_VERSIONS = {"1.0.0", "1.1.0"}


@dataclass
class StepDef:
    """单个执行步骤的结构化定义。"""
    id: str = ""
    type: str = "tool"                      # tool | subtask | condition | parallel
    tool: str = ""
    name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    condition: str = ""                     # 条件表达式，如 "{{output.step_0.success}} == true"
    retry: int = 0                          # 重试次数
    retry_delay: float = 1.0               # 重试间隔（秒）
    timeout: float = 0                      # 超时（秒），0 = 无限
    fallback_tool: str = ""                 # 失败时的回退工具
    fallback_args: Dict[str, Any] = field(default_factory=dict)
    steps: Optional[List[Dict[str, Any]]] = None  # parallel 类型时的子步骤

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("steps") is None:
            del d["steps"]
        return {k: v for k, v in d.items() if v or k in ("type", "id")}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepDef":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", "tool"),
            tool=data.get("tool", ""),
            name=data.get("name", ""),
            args=data.get("args", data.get("parameters", {})),
            parameters=data.get("parameters", {}),
            description=data.get("description", ""),
            condition=data.get("condition", ""),
            retry=int(data.get("retry", 0)),
            retry_delay=float(data.get("retry_delay", 1.0)),
            timeout=float(data.get("timeout", 0)),
            fallback_tool=data.get("fallback_tool", ""),
            fallback_args=data.get("fallback_args", {}),
            steps=data.get("steps"),
        )


@dataclass
class SkillCapsule:
    """
    本地可执行的 EvoMap Skill Capsule。
    必需: id, description, inputs, outputs, procedure 或 steps。
    可选: task_type, tags, capability, gene, metadata, signature（兼容 EvoMap 规范）。
    """

    id: str
    description: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    procedure: Optional[List[Dict[str, Any]]] = None
    steps: Optional[List[Dict[str, Any]]] = None
    task_type: str = ""
    tags: List[str] = field(default_factory=list)
    capability: List[str] = field(default_factory=list)
    gene: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[Dict[str, Any]] = None
    schema_version: str = CAPSULE_SKILL_SCHEMA_VERSION
    trusted: str = "local_source"
    priority: int = 0                       # 0=normal, 1=high, -1=low
    version: str = "1.0.0"
    author: str = ""
    source: str = ""                        # local / url / github
    created_at: float = field(default_factory=time.time)

    def get_steps(self) -> List[Dict[str, Any]]:
        """统一返回步骤列表（procedure 或 steps）。"""
        if self.procedure:
            return self.procedure
        if self.steps:
            return self.steps
        return []

    def get_step_defs(self) -> List[StepDef]:
        """返回结构化的 StepDef 列表。"""
        return [StepDef.from_dict(s) for s in self.get_steps()]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["trusted"] = self.trusted
        return d

    def to_summary(self) -> Dict[str, Any]:
        """返回轻量摘要（用于列表展示）。"""
        return {
            "id": self.id,
            "description": self.description,
            "task_type": self.task_type,
            "tags": self.tags,
            "capability": self.capability,
            "priority": self.priority,
            "version": self.version,
            "trusted": self.trusted,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillCapsule":
        procedure = data.get("procedure")
        steps = data.get("steps")
        if procedure is None and steps is None:
            procedure = []
        return cls(
            id=data.get("id", ""),
            description=data.get("description", ""),
            inputs=data.get("inputs", {}),
            outputs=data.get("outputs", {}),
            procedure=procedure,
            steps=steps,
            task_type=data.get("task_type", ""),
            tags=data.get("tags", []),
            capability=data.get("capability", []),
            gene=data.get("gene", ""),
            metadata=data.get("metadata", {}),
            signature=data.get("signature"),
            schema_version=data.get("schema_version", CAPSULE_SKILL_SCHEMA_VERSION),
            trusted=data.get("trusted", "local_source"),
            priority=int(data.get("priority", 0)),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            source=data.get("source", data.get("_source", "")),
            created_at=float(data.get("created_at", time.time())),
        )


def is_evomap_capsule_format(data: Dict[str, Any]) -> bool:
    """
    判断是否为 EvoMap Capsule 格式（GEP 或 Skill）。
    GEP: 有 trigger, gene, summary, type=Capsule
    Skill: 有 id, description, inputs, outputs, 且有 procedure 或 steps
    """
    if not isinstance(data, dict):
        return False
    # Skill 格式
    if data.get("id") and data.get("description") is not None:
        if isinstance(data.get("inputs"), dict) and isinstance(data.get("outputs"), dict):
            if "procedure" in data or "steps" in data:
                return True
    # GEP Capsule 格式（可转换为 Skill）
    if data.get("trigger") is not None and data.get("gene") is not None and data.get("summary") is not None:
        return True
    return False


def gep_capsule_to_skill(gep_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 GEP Capsule（trigger/gene/summary 格式）转换为 SkillCapsule 格式。
    GEP Capsule 没有 inputs/outputs/procedure，因此生成占位结构。
    """
    if not isinstance(gep_data, dict):
        return None
    trigger = gep_data.get("trigger", [])
    gene = gep_data.get("gene", "")
    summary = gep_data.get("summary", "")
    capsule_id = gep_data.get("id", f"gep_{gene}_{int(time.time() * 1000)}")

    if not gene and not summary:
        return None

    strategy = gep_data.get("strategy", [])
    steps = []
    for i, s in enumerate(strategy if isinstance(strategy, list) else []):
        steps.append({
            "id": f"step_{i}",
            "type": "subtask",
            "description": s if isinstance(s, str) else str(s),
        })

    return {
        "id": capsule_id,
        "description": summary or f"GEP strategy: {gene}",
        "inputs": {"task": {"type": "string", "description": "Task description"}},
        "outputs": {"result": {"type": "object", "description": "Execution result"}},
        "procedure": steps or [{"id": "step_0", "type": "subtask", "description": summary}],
        "task_type": gep_data.get("category", ""),
        "tags": list(trigger) if isinstance(trigger, list) else [],
        "capability": list(trigger) if isinstance(trigger, list) else [],
        "gene": gene,
        "metadata": {
            "original_type": "GEP_Capsule",
            "confidence": gep_data.get("confidence", 0.85),
            "env_fingerprint": gep_data.get("env_fingerprint", {}),
        },
        "schema_version": CAPSULE_SKILL_SCHEMA_VERSION,
        "priority": 0,
        "source": gep_data.get("_source", "gep_converted"),
    }


def skill_to_gep_capsule(skill: SkillCapsule) -> Dict[str, Any]:
    """将 SkillCapsule 转换为 GEP Capsule 格式（用于发布到 EvoMap 网络）。"""
    strategy = []
    for step in skill.get_steps():
        desc = step.get("description", "")
        tool = step.get("tool", step.get("name", ""))
        if desc:
            strategy.append(desc)
        elif tool:
            strategy.append(f"Execute tool: {tool}")

    return {
        "id": skill.id,
        "trigger": skill.tags or skill.capability or [],
        "gene": skill.gene or f"gene_{skill.id}",
        "summary": skill.description,
        "confidence": skill.metadata.get("confidence", 0.85) if skill.metadata else 0.85,
        "type": "Capsule",
        "strategy": strategy,
    }


def is_schema_compatible(version: str) -> bool:
    """检查 schema 版本是否兼容。"""
    return version in COMPATIBLE_SCHEMA_VERSIONS or version.startswith("1.")
