"""
Capsule Strategy — 双策略技能加载调度。

Strategy 1 (EvoMap): 当 EVOMAP_AUTH_CODE 存在时使用 EvoMap 官方网络获取 Capsule。
                      预留位 — 等拿到授权码后激活。

Strategy 2 (Open Skills): 默认策略。从公开 GitHub 仓库（anthropics/skills、
                           skillcreatorai/Ai-Agent-Skills 等）拉取 Agent Skills
                           (SKILL.md) 并转换为本地 SkillCapsule。

始终加载: 本地 ./capsules/ 目录中的手写 Capsule JSON。

调度逻辑:
  1. 加载本地 ./capsules/ + 已有缓存（始终，不阻塞）
  2. 校验 + 注册到 CapsuleRegistry（用户可立即使用已缓存技能）
  3. Open Skills: sync 在后台执行，不阻塞启动
  4. EvoMap: 仍同步执行 sync
"""

import asyncio
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
    run_sync: bool = True,
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

    # ── Step 1: 本地 + 已有缓存（不阻塞，用户可立即使用）──
    local_raw = load_all_local(
        capsules_dir=capsules_dir or DEFAULT_CAPSULES_DIR,
        cache_dir=cache_dir or DEFAULT_CAPSULES_CACHE,
    )
    result["local"]["loaded"] = len(local_raw)
    remote_raw = _load_remote_cache(strategy, cache_dir)

    # 合并并去重（按 id，后加载覆盖）
    by_id: Dict[str, Dict[str, Any]] = {}
    for c in local_raw:
        cid = c.get("id") or c.get("gene") or ""
        if cid:
            by_id[cid] = c
    for c in remote_raw:
        cid = c.get("id") or c.get("gene") or ""
        if cid:
            by_id[cid] = c
    all_raw = list(by_id.values())
    result["total_loaded"] = len(all_raw)

    # ── Step 2: 校验 + 注册（立即生效）──
    validated = validate_capsules(all_raw, allow_gep_conversion=True, check_safety=True)
    registry = get_capsule_registry()
    registered = registry.register_many(validated)
    result["registered"] = registered

    logger.info(
        f"Capsule strategy [{strategy}]: "
        f"local={result['local']['loaded']}, remote_cache={len(remote_raw)}, "
        f"registered={registered}"
    )

    # ── Step 3: 远程 sync（Open Skills 按需模式下只同步索引；EvoMap 仍同步）──
    if run_sync:
        if strategy == "evomap":
            result["remote"] = await _run_evomap_strategy(cache_dir)
        else:
            # 检查是否启用按需拉取 — 若是，只同步轻量索引，不全量拉取 SKILL.md
            on_demand_enabled = True
            try:
                from app_state import ENABLE_ON_DEMAND_SKILL_FETCH
                on_demand_enabled = ENABLE_ON_DEMAND_SKILL_FETCH
            except ImportError:
                import os
                on_demand_enabled = os.environ.get("MACAGENT_ENABLE_ON_DEMAND_SKILL_FETCH", "true").lower() not in ("false", "0", "no")

            if on_demand_enabled:
                # 按需模式：仅拉取轻量 skill_index（单次 HTTP），不全量下载 SKILL.md
                result["remote"] = {"type": "open_skills", "sync": "on_demand_mode"}
                asyncio.create_task(_background_sync_index_only(cache_dir))
            else:
                # 旧模式：后台全量同步（保持向后兼容）
                result["remote"] = {"type": "open_skills", "sync": "background_full_sync"}
                asyncio.create_task(_background_open_skills_sync(cache_dir))
    else:
        result["remote"] = {"type": strategy, "sync": "skipped"}

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


async def _background_sync_index_only(cache_dir: Optional[Path] = None) -> None:
    """
    后台仅同步轻量 skill_index（按需模式）。
    只拉取 awesome-openclaw-skills README 解析的索引 JSON（单次 HTTP ~10KB），
    让 LLM 知道有哪些在线技能，需要时再按需拉取 SKILL.md。
    """
    try:
        from .skill_index import sync_skill_index, load_cached_index
        index = load_cached_index(cache_dir)
        if index:
            logger.debug("Skill index already cached, skip background sync")
            return
        ok, total = await sync_skill_index(cache_dir)
        if ok:
            logger.info(f"Skill index ready (on-demand mode): {total} skills indexed, 0 downloaded")
        else:
            logger.debug("Skill index sync failed (non-critical, on-demand still works via direct fetch)")
    except Exception as e:
        logger.debug(f"Background index sync error: {e}")


async def _background_open_skills_sync(cache_dir: Optional[Path] = None) -> None:
    """
    后台执行 Open Skills sync；完成后增量更新 registry，使新拉取的技能立即可用。
    """
    try:
        sync_result = await _run_open_skills_strategy(cache_dir)
        if "error" in sync_result:
            logger.warning(f"Open skills background sync failed: {sync_result['error']}")
            return
        # 增量加载新缓存并注册
        try:
            from .open_skill_sources import load_cached_open_skills
            new_raw = load_cached_open_skills(cache_dir)
            if new_raw:
                validated = validate_capsules(new_raw, allow_gep_conversion=True, check_safety=True)
                registry = get_capsule_registry()
                added = registry.register_many(validated)
                if added > 0:
                    logger.info(f"Open skills sync complete: {added} new capsules registered")
        except Exception as e:
            logger.debug(f"Incremental registry update skipped: {e}")
    except Exception as e:
        logger.warning(f"Open skills background sync error: {e}")


async def _run_open_skills_strategy(cache_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Strategy 2: 从公开 GitHub 仓库拉取 Agent Skills。
    先拉取 VoltAgent/awesome-openclaw-skills 索引（轻量、快速），再拉取 SKILL.md。
    """
    try:
        from .open_skill_sources import sync_open_skill_sources
        from .skill_index import sync_skill_index
        sync_result: Dict[str, Any] = {}
        # 先拉取 awesome 索引（单次 HTTP，秒级），确保 prompt 能注入
        try:
            ok, total = await sync_skill_index(cache_dir)
            if ok:
                sync_result["skill_index"] = {"synced": True, "total": total}
        except Exception as ei:
            logger.debug(f"Skill index sync skipped: {ei}")
        sync_result.update(await sync_open_skill_sources(cache_dir=cache_dir))
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

    result = await execute_strategy(
        capsules_dir, cache_dir, force_strategy=force_strategy, run_sync=run_sync
    )

    result["previous_count"] = previous
    return result
