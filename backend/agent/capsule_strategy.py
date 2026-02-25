"""
Capsule Strategy — 双策略技能加载调度。

Strategy 1 (EvoMap): 当 EVOMAP_AUTH_CODE 存在时使用 EvoMap 官方网络获取 Capsule。
                      预留位 — 等拿到授权码后激活。

Strategy 2 (Open Skills): 默认策略。从公开 GitHub 仓库（anthropics/skills、
                           skillcreatorai/Ai-Agent-Skills 等）拉取 Agent Skills
                           (SKILL.md) 并转换为本地 SkillCapsule。

始终加载: 本地 ./capsules/ 目录中的手写 Capsule JSON。

调度逻辑:
  1. 加载本地 ./capsules/（始终）
  2. 如果 Strategy 1 可用 → 使用 EvoMap sync
  3. 否则 → Strategy 2: sync_open_skill_sources
  4. 校验 + 注册到 CapsuleRegistry
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capsule_loader import DEFAULT_CAPSULES_DIR, DEFAULT_CAPSULES_CACHE, load_all_local
from .capsule_validator import validate_capsules
from .capsule_registry import get_capsule_registry, reset_capsule_registry

logger = logging.getLogger(__name__)

EVOMAP_AUTH_CODE_ENV = "EVOMAP_AUTH_CODE"


def get_active_strategy() -> str:
    """
    判断当前应使用的策略。
    返回 "evomap" 或 "open_skills"。
    当 ENABLE_EVOMAP=false 时仅使用 open_skills（本地 + 开放技能源）。
    """
    if os.environ.get("ENABLE_EVOMAP", "false").lower() != "true":
        return "open_skills"
    auth_code = os.environ.get(EVOMAP_AUTH_CODE_ENV, "").strip()
    if auth_code:
        return "evomap"
    return "open_skills"


async def execute_strategy(
    capsules_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    force_strategy: Optional[str] = None,
    start_scheduler: bool = False,
) -> Dict[str, Any]:
    """
    按策略优先级加载技能：
      1. 本地 ./capsules/（始终）
      2. Strategy 1 (EvoMap) 或 Strategy 2 (Open Skills)
    返回 { "strategy", "local", "remote", "registered", ... }
    """
    strategy = force_strategy or get_active_strategy()
    result: Dict[str, Any] = {
        "strategy": strategy,
        "local": {"loaded": 0},
        "remote": None,
        "registered": 0,
        "total_loaded": 0,
    }

    # ── Step 1: 本地 Capsule（始终加载）──
    local_raw = load_all_local(
        capsules_dir=capsules_dir or DEFAULT_CAPSULES_DIR,
        cache_dir=cache_dir or DEFAULT_CAPSULES_CACHE,
    )
    result["local"]["loaded"] = len(local_raw)
    all_raw = list(local_raw)

    # ── Step 2: 按策略拉取远程技能 ──
    if strategy == "evomap":
        result["remote"] = await _run_evomap_strategy(cache_dir)
    else:
        result["remote"] = await _run_open_skills_strategy(cache_dir)

    # 加载远程缓存
    remote_raw = _load_remote_cache(strategy, cache_dir)
    all_raw.extend(remote_raw)

    result["total_loaded"] = len(all_raw)

    # ── Step 3: 校验 + 注册 ──
    validated = validate_capsules(all_raw, allow_gep_conversion=True, check_safety=True)
    registry = get_capsule_registry()
    registered = registry.register_many(validated)
    result["registered"] = registered

    logger.info(
        f"Capsule strategy [{strategy}]: "
        f"local={result['local']['loaded']}, remote={len(remote_raw)}, "
        f"registered={registered}"
    )

    # ── Step 4: 可选定时刷新 ──
    if start_scheduler:
        try:
            from .capsule_sync import get_sync_scheduler
            scheduler = get_sync_scheduler()
            scheduler.start()
        except Exception as e:
            logger.warning(f"Scheduler start failed: {e}")

    return result


async def _run_evomap_strategy(cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Strategy 1: EvoMap 网络同步。
    预留位 — 当 EVOMAP_AUTH_CODE 可用时调用 EvoMap capsule sync。
    """
    try:
        from .capsule_sync import sync_capsules_from_sources
        sync_result = await sync_capsules_from_sources(cache_dir=cache_dir)
        return {"type": "evomap", "sync": sync_result}
    except Exception as e:
        logger.warning(f"EvoMap strategy failed, falling back to open_skills: {e}")
        return await _run_open_skills_strategy(cache_dir)


async def _run_open_skills_strategy(cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Strategy 2: 从公开 GitHub 仓库拉取 Agent Skills。
    """
    try:
        from .open_skill_sources import sync_open_skill_sources
        sync_result = await sync_open_skill_sources(cache_dir=cache_dir)
        return {"type": "open_skills", "sync": sync_result}
    except Exception as e:
        logger.warning(f"Open skills strategy failed: {e}")
        return {"type": "open_skills", "error": str(e)}


def _load_remote_cache(strategy: str, cache_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """加载远程策略的缓存文件。"""
    if strategy == "open_skills":
        try:
            from .open_skill_sources import load_cached_open_skills
            return load_cached_open_skills(cache_dir)
        except Exception:
            return []
    # evomap 策略的远程缓存已经在 load_all_local 的 capsules_cache 里
    return []


async def reload_with_strategy(
    capsules_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    force_strategy: Optional[str] = None,
    run_sync: bool = True,
) -> Dict[str, Any]:
    """热重载：重置注册表，重新按策略加载。"""
    registry = get_capsule_registry()
    previous = len(registry)
    reset_capsule_registry()

    if run_sync:
        result = await execute_strategy(capsules_dir, cache_dir, force_strategy)
    else:
        # 只加载本地+缓存，不拉取远程
        result = await execute_strategy(capsules_dir, cache_dir, force_strategy=force_strategy)

    result["previous_count"] = previous
    return result
