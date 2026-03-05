"""
Capsule Bootstrap - 启动时加载并注册本地 + 远程 Capsule。
使用双策略调度（capsule_strategy）：
  Strategy 1 (EvoMap): 当 EVOMAP_AUTH_CODE 存在时 → EvoMap 网络 sync
  Strategy 2 (Open Skills): 默认 → 从 anthropics/skills 等公开 GitHub 仓库拉取
  始终加载: 本地 ./capsules/ 目录中的手写 Capsule JSON

支持热重载。
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .capsule_strategy import execute_strategy, reload_with_strategy, get_active_strategy

logger = logging.getLogger(__name__)


async def bootstrap_capsules(
    capsules_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    run_sync_first: bool = True,
    start_scheduler: bool = False,
    scheduler_interval: int = 3600,
    force_strategy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    启动入口：按策略优先级加载本地+远程技能。

    按需拉取模式（ENABLE_ON_DEMAND_SKILL_FETCH=true，默认）：
      - 不全量同步 GitHub 技能
      - 只加载本地 ./capsules/ + 已缓存技能
      - 后台异步同步轻量 skill_index（约 10KB，供 LLM 了解可用技能列表）
      - 首次用到某技能时才按需拉取对应 SKILL.md

    全量同步模式（ENABLE_ON_DEMAND_SKILL_FETCH=false，可选）：
      - 启动时从 GitHub 拉取全量技能（旧行为）

    兼容旧签名 bootstrap_capsules(run_sync_first=True)。
    """
    # 读取按需模式 Flag
    on_demand = True
    try:
        from app_state import ENABLE_ON_DEMAND_SKILL_FETCH
        on_demand = ENABLE_ON_DEMAND_SKILL_FETCH
    except ImportError:
        import os
        on_demand = os.environ.get("MACAGENT_ENABLE_ON_DEMAND_SKILL_FETCH", "true").lower() not in ("false", "0", "no")

    # 按需模式：强制 run_sync_first=False，只加载本地+缓存+后台索引
    if on_demand:
        run_sync_first = False
        logger.info("Capsule bootstrap: on-demand mode (no bulk GitHub sync at startup)")

    strategy = force_strategy or get_active_strategy()
    logger.info(f"Capsule bootstrap starting (strategy={strategy}, sync={run_sync_first})")

    if not run_sync_first:
        # 仅加载本地+已有缓存，不拉取远程
        from .capsule_loader import DEFAULT_CAPSULES_DIR, DEFAULT_CAPSULES_CACHE, load_all_local
        from .capsule_validator import validate_capsules
        from .capsule_registry import get_capsule_registry

        raw = load_all_local(
            capsules_dir=capsules_dir or DEFAULT_CAPSULES_DIR,
            cache_dir=cache_dir or DEFAULT_CAPSULES_CACHE,
        )
        # 也加载开源技能缓存
        try:
            from .open_skill_sources import load_cached_open_skills
            raw.extend(load_cached_open_skills(cache_dir))
        except Exception:
            pass

        # 轻量同步：若索引不存在则拉取（单次 HTTP，秒级），供 prompt 注入「在线技能」提示
        try:
            from .skill_index import sync_skill_index, load_cached_index
            if not load_cached_index(cache_dir):
                await sync_skill_index(cache_dir)
        except Exception:
            pass

        validated = validate_capsules(raw, allow_gep_conversion=True, check_safety=True)
        registry = get_capsule_registry()
        registered = registry.register_many(validated)

        return {
            "strategy": strategy,
            "loaded": len(raw),
            "registered": registered,
            "sync": None,
            "scheduler": "off",
        }

    result = await execute_strategy(
        capsules_dir=capsules_dir,
        cache_dir=cache_dir,
        force_strategy=force_strategy,
        start_scheduler=start_scheduler,
    )

    # 兼容旧字段名
    result.setdefault("loaded", result.get("total_loaded", 0))
    result.setdefault("sync", result.get("remote"))
    result.setdefault("scheduler", "started" if start_scheduler else "off")

    return result


async def reload_capsules(
    capsules_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    run_sync: bool = False,
    force_strategy: Optional[str] = None,
) -> Dict[str, Any]:
    """热重载：清空注册表，重新按策略加载。"""
    return await reload_with_strategy(
        capsules_dir=capsules_dir,
        cache_dir=cache_dir,
        force_strategy=force_strategy,
        run_sync=run_sync,
    )
