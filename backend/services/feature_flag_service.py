"""
FeatureFlag 统一管理服务
支持：读取所有 Flag、热更新、持久化到 data/config/feature_flags.json。
优先级：运行时热更新 > feature_flags.json > 环境变量 > 代码默认值。
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import app_state

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "config"
_FF_FILE = _DATA_DIR / "feature_flags.json"

# Flag 元数据注册表：{flag_name: {type, default, env_var, description}}
_FLAG_REGISTRY: List[Dict[str, Any]] = [
    # v3.0
    {"name": "ENABLE_EVOMAP", "type": "bool", "default": False, "env": "ENABLE_EVOMAP", "desc": "EvoMap 服务启用"},
    {"name": "AUTO_TOOL_UPGRADE", "type": "bool", "default": True, "env": "MACAGENT_AUTO_TOOL_UPGRADE", "desc": "工具自动升级"},
    {"name": "ENABLE_LANGCHAIN_COMPAT", "type": "bool", "default": True, "env": "ENABLE_LANGCHAIN_COMPAT", "desc": "LangChain 兼容模式"},
    # v3.1
    {"name": "USE_SUMMARIZED_CONTEXT", "type": "bool", "default": True, "env": "MACAGENT_USE_SUMMARIZED_CONTEXT", "desc": "使用压缩上下文"},
    {"name": "ENABLE_PLAN_AND_EXECUTE", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_PLAN_AND_EXECUTE", "desc": "Plan-and-Execute 分离"},
    {"name": "ENABLE_MID_LOOP_REFLECTION", "type": "bool", "default": True, "env": "MACAGENT_ENABLE_MID_LOOP_REFLECTION", "desc": "中途反思启用"},
    {"name": "GOAL_RESTATE_EVERY_N", "type": "int", "default": 6, "env": "MACAGENT_GOAL_RESTATE_EVERY_N", "desc": "每 N 步重述目标"},
    {"name": "MID_LOOP_REFLECTION_EVERY_N", "type": "int", "default": 5, "env": "MACAGENT_MID_LOOP_REFLECTION_EVERY_N", "desc": "每 N 步触发中途反思"},
    {"name": "ESCALATION_FORCE_AFTER_N", "type": "int", "default": 2, "env": "MACAGENT_ESCALATION_FORCE_AFTER_N", "desc": "连续 N 次失败触发强制切换"},
    {"name": "ESCALATION_SKILL_AFTER_N", "type": "int", "default": 3, "env": "MACAGENT_ESCALATION_SKILL_AFTER_N", "desc": "连续 N 次失败触发 Skill 降级"},
    {"name": "ESCALATION_SIMILARITY_THRESHOLD", "type": "float", "default": 0.85, "env": "MACAGENT_ESCALATION_SIMILARITY_THRESHOLD", "desc": "相似度阈值"},
    # v3.2
    {"name": "TRACE_TOKEN_STATS", "type": "bool", "default": True, "env": "MACAGENT_TRACE_TOKEN_STATS", "desc": "Trace 记录 Token 统计"},
    {"name": "TRACE_TOOL_CALLS", "type": "bool", "default": True, "env": "MACAGENT_TRACE_TOOL_CALLS", "desc": "Trace 记录工具调用"},
    {"name": "HEALTH_DEEP_LLM_TIMEOUT", "type": "float", "default": 5.0, "env": "MACAGENT_HEALTH_DEEP_LLM_TIMEOUT", "desc": "/health/deep LLM 超时"},
    {"name": "ENABLE_IDEMPOTENT_TASKS", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_IDEMPOTENT_TASKS", "desc": "幂等任务"},
    {"name": "ENABLE_IMPORTANCE_WEIGHTED_MEMORY", "type": "bool", "default": True, "env": "MACAGENT_ENABLE_IMPORTANCE_WEIGHTED_MEMORY", "desc": "重要性加权 Memory"},
    {"name": "ENABLE_FAILURE_TYPE_REFLECTION", "type": "bool", "default": True, "env": "MACAGENT_ENABLE_FAILURE_TYPE_REFLECTION", "desc": "失败分类反思"},
    {"name": "ENABLE_EXTENDED_THINKING", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_EXTENDED_THINKING", "desc": "Extended Thinking/CoT"},
    {"name": "EXTENDED_THINKING_BUDGET_TOKENS", "type": "int", "default": 8000, "env": "MACAGENT_EXTENDED_THINKING_BUDGET_TOKENS", "desc": "Extended Thinking token 预算"},
    {"name": "ENABLE_SUBAGENT", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_SUBAGENT", "desc": "子 Agent 调度"},
    {"name": "ENABLE_ON_DEMAND_SKILL_FETCH", "type": "bool", "default": True, "env": "MACAGENT_ENABLE_ON_DEMAND_SKILL_FETCH", "desc": "Skill 按需拉取"},
    {"name": "ON_DEMAND_SKILL_FETCH_TIMEOUT", "type": "float", "default": 10.0, "env": "MACAGENT_ON_DEMAND_SKILL_FETCH_TIMEOUT", "desc": "按需拉取超时"},
    {"name": "ON_DEMAND_SKILL_MAX_FETCH", "type": "int", "default": 3, "env": "MACAGENT_ON_DEMAND_SKILL_MAX_FETCH", "desc": "单次最多拉取技能数"},
    # v3.3
    {"name": "ENABLE_HITL", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_HITL", "desc": "HITL 人工审批"},
    {"name": "HITL_CONFIRMATION_TIMEOUT", "type": "int", "default": 120, "env": "MACAGENT_HITL_CONFIRMATION_TIMEOUT", "desc": "HITL 确认超时（秒）"},
    {"name": "ENABLE_AUDIT_LOG", "type": "bool", "default": True, "env": "MACAGENT_ENABLE_AUDIT_LOG", "desc": "统一审计日志"},
    {"name": "AUDIT_LOG_MAX_SIZE_MB", "type": "int", "default": 100, "env": "MACAGENT_AUDIT_LOG_MAX_SIZE_MB", "desc": "审计日志最大磁盘占用 MB"},
    {"name": "IDEMPOTENT_CACHE_TTL", "type": "int", "default": 86400, "env": "MACAGENT_IDEMPOTENT_CACHE_TTL", "desc": "幂等缓存过期秒数"},
    {"name": "ENABLE_SESSION_RESUME", "type": "bool", "default": False, "env": "MACAGENT_ENABLE_SESSION_RESUME", "desc": "Session Resume/Fork"},
    {"name": "SUBAGENT_MAX_CONCURRENT", "type": "int", "default": 3, "env": "MACAGENT_SUBAGENT_MAX_CONCURRENT", "desc": "子 Agent 最大并行数"},
    {"name": "SUBAGENT_TIMEOUT", "type": "int", "default": 300, "env": "MACAGENT_SUBAGENT_TIMEOUT", "desc": "子 Agent 超时（秒）"},
]


def _load_persisted() -> Dict[str, Any]:
    """从磁盘加载持久化 Flag 值"""
    if not _FF_FILE.exists():
        return {}
    try:
        with open(_FF_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load feature_flags.json: %s", e)
        return {}


def _save_persisted(data: Dict[str, Any]) -> None:
    """将 Flag 值持久化到磁盘"""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _FF_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(_FF_FILE)


def _cast_value(val: Any, flag_type: str) -> Any:
    """将值转换为目标类型"""
    if flag_type == "bool":
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")
    if flag_type == "int":
        return int(val)
    if flag_type == "float":
        return float(val)
    return val


def _get_current_value(name: str) -> Any:
    """从 app_state 获取 Flag 当前运行值"""
    return getattr(app_state, name, None)


def _set_runtime_value(name: str, value: Any) -> bool:
    """热更新 app_state 中的 Flag 值"""
    if not hasattr(app_state, name):
        return False
    setattr(app_state, name, value)
    return True


def get_all_flags() -> List[Dict[str, Any]]:
    """返回所有 Flag 的当前状态"""
    persisted = _load_persisted()
    result = []
    for meta in _FLAG_REGISTRY:
        name = meta["name"]
        current = _get_current_value(name)
        # 判断来源
        env_val = os.environ.get(meta["env"])
        if name in persisted:
            source = "config"
        elif env_val is not None:
            source = "env"
        else:
            source = "default"
        result.append({
            "name": name,
            "type": meta["type"],
            "default": meta["default"],
            "current": current,
            "source": source,
            "env_var": meta["env"],
            "description": meta["desc"],
        })
    return result


def update_flag(name: str, value: Any) -> Optional[Dict[str, Any]]:
    """
    热更新指定 Flag 值（运行时 + 持久化）。
    返回更新后的 Flag 信息；Flag 不存在返回 None。
    """
    meta = None
    for m in _FLAG_REGISTRY:
        if m["name"] == name:
            meta = m
            break
    if meta is None:
        return None

    casted = _cast_value(value, meta["type"])
    _set_runtime_value(name, casted)

    # 持久化
    persisted = _load_persisted()
    persisted[name] = casted
    _save_persisted(persisted)

    return {
        "name": name,
        "type": meta["type"],
        "current": casted,
        "source": "config",
        "env_var": meta["env"],
        "description": meta["desc"],
    }


def reset_all_flags() -> int:
    """重置所有 Flag 为默认值，清除持久化。返回重置数量。"""
    count = 0
    for meta in _FLAG_REGISTRY:
        _set_runtime_value(meta["name"], meta["default"])
        count += 1
    # 清除持久化文件
    if _FF_FILE.exists():
        _FF_FILE.unlink()
    return count


def load_persisted_flags() -> int:
    """
    启动时调用：从 feature_flags.json 加载持久化值覆盖 app_state。
    返回加载数量。
    """
    persisted = _load_persisted()
    count = 0
    for name, value in persisted.items():
        meta = None
        for m in _FLAG_REGISTRY:
            if m["name"] == name:
                meta = m
                break
        if meta is None:
            continue
        # 环境变量优先于持久化
        env_val = os.environ.get(meta["env"])
        if env_val is not None:
            continue
        casted = _cast_value(value, meta["type"])
        if _set_runtime_value(name, casted):
            count += 1
    if count:
        logger.info("Loaded %d persisted feature flags", count)
    return count
