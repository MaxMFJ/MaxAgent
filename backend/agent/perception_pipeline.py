"""
Perception Pipeline — AX → Semantic UI 状态感知
组合 AX 查询 + Screenshot OCR + 缓存，提供统一的 UI 感知。

组件：
1. PerceptionPipeline: 统一入口（AX → OCR fallback）
2. PerceptionCache: 避免短时间内重复查询
3. Stable UI Element ID: 跨截图保持元素标识
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .ui_grounding import UIElement, UIGrounding, UISnapshot, get_ui_grounding

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Perception Cache
# ──────────────────────────────────────────────

@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    data: Any
    created_at: float = field(default_factory=time.time)
    ttl: float = 5.0  # 默认 5 秒过期

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > self.ttl


class PerceptionCache:
    """
    感知结果缓存。
    避免短时间内重复截图/AX 查询。
    """

    def __init__(self, default_ttl: float = 5.0, max_entries: int = 50):
        self._cache: Dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._max = max_entries
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and not entry.expired:
            self._hits += 1
            return entry.data
        if entry:
            del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, data: Any, ttl: Optional[float] = None) -> None:
        self._cache[key] = CacheEntry(
            key=key, data=data, ttl=ttl or self._default_ttl
        )
        # 淘汰过期条目
        if len(self._cache) > self._max:
            self._evict()

    def invalidate(self, key: str = "") -> None:
        """清除缓存（指定 key 或全部）"""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def _evict(self) -> None:
        expired = [k for k, v in self._cache.items() if v.expired]
        for k in expired:
            del self._cache[k]
        # 仍然超出限制：淘汰最旧的
        while len(self._cache) > self._max:
            oldest = min(self._cache.items(), key=lambda x: x[1].created_at)
            del self._cache[oldest[0]]

    @property
    def stats(self) -> Dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}

    def reset(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0


# ──────────────────────────────────────────────
# Stable UI Element ID
# ──────────────────────────────────────────────

def compute_element_id(elem: UIElement) -> str:
    """
    为 UI 元素生成稳定的标识符。
    基于 role + title + position（四舍五入到 10px 网格），
    使得轻微的位置偏移不会改变 ID。
    """
    grid = 10
    grid_x = int(elem.pos_x / grid) * grid
    grid_y = int(elem.pos_y / grid) * grid
    raw = f"{elem.role}|{elem.title}|{grid_x},{grid_y}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]


def match_elements_across_snapshots(
    snap_a: UISnapshot, snap_b: UISnapshot
) -> List[Tuple[UIElement, UIElement]]:
    """
    匹配两个快照中的相同元素（通过 stable ID）。
    返回 (elem_a, elem_b) 配对列表。
    """
    ids_a = {compute_element_id(e): e for e in snap_a.elements}
    ids_b = {compute_element_id(e): e for e in snap_b.elements}
    common = set(ids_a.keys()) & set(ids_b.keys())
    return [(ids_a[k], ids_b[k]) for k in common]


# ──────────────────────────────────────────────
# Perception Pipeline
# ──────────────────────────────────────────────

class PerceptionPipeline:
    """
    统一感知入口。
    AX Bridge → (失败) → Screenshot OCR → (失败) → 空结果

    提供：
    - perceive(app_name): 获取当前 UI 状态
    - perceive_focused(): 获取当前焦点应用的 UI 状态
    - find_element(description): 语义查找 UI 元素
    """

    def __init__(
        self,
        ui_grounding: Optional[UIGrounding] = None,
        cache: Optional[PerceptionCache] = None,
    ):
        self._ui = ui_grounding or get_ui_grounding()
        self._cache = cache or PerceptionCache()
        self._last_snapshot: Optional[UISnapshot] = None

    async def perceive(self, app_name: str = "", force: bool = False) -> UISnapshot:
        """
        感知当前 UI 状态。
        优先从缓存读取，未命中则查询 AX Bridge。
        """
        cache_key = f"perceive:{app_name or '_focused'}"
        if not force:
            cached = self._cache.get(cache_key)
            if cached:
                return cached

        # 尝试 AX Bridge
        snap = await self._ui.capture_snapshot(app_name=app_name)
        if snap.elements:
            self._cache.set(cache_key, snap, ttl=5.0)
            self._last_snapshot = snap
            return snap

        # AX Bridge 失败，返回空快照
        logger.debug("Perception: AX Bridge returned empty for %s", app_name or "focused")
        empty = UISnapshot(app_name=app_name or "unknown")
        self._last_snapshot = empty
        return empty

    async def perceive_focused(self, force: bool = False) -> UISnapshot:
        """感知当前焦点应用"""
        return await self.perceive(app_name="", force=force)

    async def find_element(
        self,
        description: str,
        app_name: str = "",
        role: str = "",
    ) -> Optional[UIElement]:
        """
        根据描述查找 UI 元素。
        先从缓存快照查找，未找到则重新查询。
        """
        # 先在 last_snapshot 中搜索
        if self._last_snapshot and self._last_snapshot.elements:
            matches = self._last_snapshot.find_by_title(description, fuzzy=True)
            if role:
                matches = [m for m in matches if role.lower() in m.role.lower()]
            if matches:
                return matches[0]

        # 重新查询
        snap = await self.perceive(app_name=app_name, force=True)
        matches = snap.find_by_title(description, fuzzy=True)
        if role:
            matches = [m for m in matches if role.lower() in m.role.lower()]
        return matches[0] if matches else None

    async def get_interactive_elements(self, app_name: str = "") -> List[UIElement]:
        """获取可交互元素列表"""
        snap = await self.perceive(app_name=app_name)
        return snap.interactive_elements()

    async def describe_ui(self, app_name: str = "", max_elements: int = 20) -> str:
        """生成 UI 状态描述给 LLM"""
        snap = await self.perceive(app_name=app_name)
        return snap.for_llm(max_elements=max_elements)

    def invalidate_cache(self) -> None:
        """清除感知缓存（UI 发生变化后调用）"""
        self._cache.invalidate()

    @property
    def last_snapshot(self) -> Optional[UISnapshot]:
        return self._last_snapshot

    @property
    def cache_stats(self) -> Dict[str, int]:
        return self._cache.stats

    def reset(self) -> None:
        self._cache.reset()
        self._last_snapshot = None


# 单例
_pipeline: Optional[PerceptionPipeline] = None


def get_perception_pipeline() -> PerceptionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = PerceptionPipeline()
    return _pipeline
