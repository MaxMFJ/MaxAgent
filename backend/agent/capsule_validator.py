"""
Capsule Validator - 校验 EvoMap Skill Capsule 必需字段与 schema
支持：
  - GEP Capsule 自动转换为 SkillCapsule
  - schema 版本兼容性检查
  - 步骤安全校验（禁止危险命令）
  - 校验通过后标记 trusted = local_source
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .capsule_models import (
    SkillCapsule,
    CAPSULE_SKILL_SCHEMA_VERSION,
    gep_capsule_to_skill,
    is_schema_compatible,
)

logger = logging.getLogger(__name__)

REQUIRED_KEYS = ("id", "description", "inputs", "outputs")
PROCEDURE_KEYS = ("procedure", "steps")

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bdd\s+if=", re.I),
    re.compile(r":(){ :\|:& };:", re.I),  # fork bomb
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh)\b", re.I),
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh)\b", re.I),
]


def validate_capsule(
    data: Dict[str, Any],
    allow_gep_conversion: bool = True,
    check_safety: bool = True,
) -> Tuple[bool, Optional[str], Optional[SkillCapsule]]:
    """
    校验 Capsule 必需字段并兼容 EvoMap skill 规范。
    支持 GEP Capsule 自动转换。
    返回 (ok, error_message, SkillCapsule_or_None)。
    """
    if not isinstance(data, dict):
        return False, "Capsule must be a dict", None

    # 尝试 GEP → Skill 转换
    if allow_gep_conversion and not _is_skill_format(data):
        if data.get("trigger") is not None and data.get("gene") is not None:
            converted = gep_capsule_to_skill(data)
            if converted:
                logger.debug(f"GEP Capsule converted to Skill: {converted.get('id', '?')}")
                data = converted
            else:
                return False, "GEP Capsule conversion failed", None

    for key in REQUIRED_KEYS:
        if key not in data:
            return False, f"Missing required field: {key}", None

    if not isinstance(data.get("inputs"), dict):
        return False, "inputs must be a dict", None
    if not isinstance(data.get("outputs"), dict):
        return False, "outputs must be a dict", None

    has_steps = False
    if "procedure" in data and isinstance(data["procedure"], list):
        has_steps = True
    if "steps" in data and isinstance(data["steps"], list):
        has_steps = True
    if not has_steps:
        return False, "Must have 'procedure' or 'steps' as a list", None

    # Schema 版本兼容性
    schema_ver = data.get("schema_version", CAPSULE_SKILL_SCHEMA_VERSION)
    if not is_schema_compatible(schema_ver):
        return False, f"Incompatible schema version: {schema_ver}", None

    # 安全校验
    if check_safety:
        safety_ok, safety_err = _check_step_safety(data)
        if not safety_ok:
            return False, f"Safety check failed: {safety_err}", None

    try:
        capsule = SkillCapsule.from_dict(data)
    except Exception as e:
        return False, f"Schema error: {e}", None

    capsule.trusted = "local_source"
    return True, None, capsule


def validate_capsules(
    items: List[Dict[str, Any]],
    allow_gep_conversion: bool = True,
    check_safety: bool = True,
) -> List[SkillCapsule]:
    """批量校验，返回通过校验的 SkillCapsule 列表。"""
    result: List[SkillCapsule] = []
    for i, data in enumerate(items):
        ok, err, cap = validate_capsule(
            data,
            allow_gep_conversion=allow_gep_conversion,
            check_safety=check_safety,
        )
        if ok and cap:
            result.append(cap)
        else:
            cid = data.get("id", f"#{i}")
            logger.debug(f"Capsule {cid} validation failed: {err}")
    return result


def _is_skill_format(data: Dict[str, Any]) -> bool:
    """检查是否已经是 Skill 格式。"""
    return bool(
        data.get("id")
        and data.get("description") is not None
        and isinstance(data.get("inputs"), dict)
        and isinstance(data.get("outputs"), dict)
        and ("procedure" in data or "steps" in data)
    )


def _check_step_safety(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """检查步骤中是否包含危险命令。"""
    steps = data.get("procedure", data.get("steps", []))
    if not isinstance(steps, list):
        return True, None

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        args = step.get("args", step.get("parameters", {}))
        if not isinstance(args, dict):
            continue
        for key, value in args.items():
            if isinstance(value, str):
                for pattern in DANGEROUS_PATTERNS:
                    if pattern.search(value):
                        return False, f"Step {i} arg '{key}' contains dangerous command: {value[:100]}"

        sub_steps = step.get("steps", [])
        if isinstance(sub_steps, list):
            for j, sub in enumerate(sub_steps):
                if isinstance(sub, dict):
                    sub_args = sub.get("args", sub.get("parameters", {}))
                    if isinstance(sub_args, dict):
                        for key, value in sub_args.items():
                            if isinstance(value, str):
                                for pattern in DANGEROUS_PATTERNS:
                                    if pattern.search(value):
                                        return False, f"Step {i}.{j} arg '{key}' contains dangerous command"

    return True, None
