"""
Capsule Registry - 本地 Capsule 库
按 capability / task_type / tags 建立索引，支持加权模糊搜索、版本管理、热更新、统计。
不依赖 EvoMap 网络 API，不需要注册节点或邀请码。
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .capsule_models import SkillCapsule

logger = logging.getLogger(__name__)


class CapsuleRegistry:
    """
    本地 Capsule 注册表。
    支持：
      - 按 id / task_type / capability / tags 索引
      - 加权模糊搜索（description + tags + capability 综合评分）
      - 版本管理（同 id 保留最新版本）
      - 热更新（register 覆盖旧版本并重建索引）
      - 使用统计（execute_count / last_used）
    """

    def __init__(self):
        self._by_id: Dict[str, SkillCapsule] = {}
        self._by_task: Dict[str, List[str]] = {}       # task_type -> [capsule_ids]
        self._by_capability: Dict[str, List[str]] = {}  # capability -> [capsule_ids]
        self._by_tag: Dict[str, List[str]] = {}         # tag -> [capsule_ids]
        self._stats: Dict[str, Dict[str, Any]] = {}     # capsule_id -> {execute_count, last_used, ...}

    def register(self, capsule: SkillCapsule) -> bool:
        """
        注册单个 Capsule，建立索引。
        如果已存在同 id 的 Capsule，比较版本号，保留较新版本。
        返回 True 表示注册成功（新增或更新）。
        """
        cid = capsule.id
        if not cid:
            logger.warning("Capsule has no id, skip registration")
            return False

        existing = self._by_id.get(cid)
        if existing:
            if _version_compare(capsule.version, existing.version) < 0:
                logger.debug(f"Capsule {cid} v{capsule.version} older than existing v{existing.version}, skip")
                return False
            self._remove_from_indexes(cid)

        self._by_id[cid] = capsule

        task = (capsule.task_type or "").strip().lower()
        if task:
            self._by_task.setdefault(task, []).append(cid)

        for cap in capsule.capability or []:
            key = (cap or "").strip().lower()
            if key:
                self._by_capability.setdefault(key, []).append(cid)

        for tag in capsule.tags or []:
            key = (tag or "").strip().lower()
            if key:
                self._by_tag.setdefault(key, []).append(cid)

        if cid not in self._stats:
            self._stats[cid] = {"execute_count": 0, "last_used": 0, "registered_at": time.time()}

        action = "updated" if existing else "registered"
        logger.debug(f"Capsule {action}: {cid} v{capsule.version} (task_type={task}, tags={len(capsule.tags or [])})")
        return True

    def register_many(self, capsules: List[SkillCapsule]) -> int:
        """批量注册，返回成功注册数。"""
        count = 0
        for c in capsules:
            if self.register(c):
                count += 1
        return count

    def unregister(self, capsule_id: str) -> bool:
        """移除一个 Capsule。"""
        if capsule_id not in self._by_id:
            return False
        self._remove_from_indexes(capsule_id)
        del self._by_id[capsule_id]
        self._stats.pop(capsule_id, None)
        return True

    def get_capsule(self, id: str) -> Optional[SkillCapsule]:
        return self._by_id.get(id)

    def list_capsules(self) -> List[SkillCapsule]:
        return list(self._by_id.values())

    def find_capsule_by_task(
        self,
        task: str,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> List[SkillCapsule]:
        """
        按任务描述加权模糊搜索 Capsule。
        评分规则：
          - 精确 task_type 匹配: +3.0
          - capability 包含关键词: +2.0
          - tag 包含关键词: +1.5
          - description 包含关键词: +1.0
          - priority 加成: +0.5 * priority
          - 使用频率加成: +0.1 * min(execute_count, 10)
        返回按分数降序排列的列表。
        """
        task_lower = (task or "").strip().lower()
        if not task_lower:
            return []

        keywords = _extract_keywords(task_lower)
        scored: Dict[str, float] = {}

        for kw in keywords:
            for cid in self._by_task.get(kw, []):
                scored[cid] = scored.get(cid, 0) + 3.0

            for key, cids in self._by_capability.items():
                if kw in key or key in kw:
                    for cid in cids:
                        scored[cid] = scored.get(cid, 0) + 2.0

            for key, cids in self._by_tag.items():
                if kw in key or key in kw:
                    for cid in cids:
                        scored[cid] = scored.get(cid, 0) + 1.5

        for cid, cap in self._by_id.items():
            desc_lower = (cap.description or "").lower()
            for kw in keywords:
                if kw in desc_lower:
                    scored[cid] = scored.get(cid, 0) + 1.0

        for cid in scored:
            cap = self._by_id.get(cid)
            if cap:
                scored[cid] += 0.5 * cap.priority
            stats = self._stats.get(cid, {})
            scored[cid] += 0.1 * min(stats.get("execute_count", 0), 10)

        ranked = [(cid, score) for cid, score in scored.items() if score >= min_score]
        ranked.sort(key=lambda x: -x[1])

        result = []
        for cid, _ in ranked[:limit]:
            cap = self._by_id.get(cid)
            if cap:
                result.append(cap)
        return result

    def record_execution(self, capsule_id: str, success: bool = True) -> None:
        """记录 Capsule 执行统计。"""
        if capsule_id not in self._stats:
            self._stats[capsule_id] = {"execute_count": 0, "last_used": 0, "registered_at": time.time()}
        self._stats[capsule_id]["execute_count"] += 1
        self._stats[capsule_id]["last_used"] = time.time()
        if success:
            self._stats[capsule_id]["success_count"] = self._stats[capsule_id].get("success_count", 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        """返回注册表统计信息。"""
        total = len(self._by_id)
        total_executions = sum(s.get("execute_count", 0) for s in self._stats.values())
        by_source: Dict[str, int] = {}
        for cap in self._by_id.values():
            src = cap.source or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
        return {
            "total_capsules": total,
            "total_executions": total_executions,
            "by_source": by_source,
            "by_task_type": {k: len(v) for k, v in self._by_task.items()},
            "top_used": sorted(
                [(cid, s.get("execute_count", 0)) for cid, s in self._stats.items()],
                key=lambda x: -x[1],
            )[:10],
        }

    def clear(self) -> None:
        self._by_id.clear()
        self._by_task.clear()
        self._by_capability.clear()
        self._by_tag.clear()
        self._stats.clear()

    def _remove_from_indexes(self, capsule_id: str) -> None:
        """从所有索引中移除指定 id。"""
        for idx in (self._by_task, self._by_capability, self._by_tag):
            for key in list(idx.keys()):
                if capsule_id in idx[key]:
                    idx[key].remove(capsule_id)
                    if not idx[key]:
                        del idx[key]

    def __len__(self) -> int:
        return len(self._by_id)


def _extract_keywords(text: str) -> List[str]:
    """从文本中提取搜索关键词。"""
    import re
    words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    stop_words = {"的", "了", "在", "是", "我", "要", "请", "把", "用", "和", "a", "the", "to", "is", "for", "and"}
    return [w for w in words if w not in stop_words and len(w) > 1]


def _version_compare(v1: str, v2: str) -> int:
    """比较两个语义版本号。返回 >0 表示 v1 更新，<0 表示 v2 更新，0 表示相同。"""
    def _parts(v):
        try:
            return [int(x) for x in (v or "0.0.0").split(".")]
        except ValueError:
            return [0, 0, 0]
    p1, p2 = _parts(v1), _parts(v2)
    for a, b in zip(p1, p2):
        if a != b:
            return a - b
    return len(p1) - len(p2)


_registry: Optional[CapsuleRegistry] = None


def get_capsule_registry() -> CapsuleRegistry:
    global _registry
    if _registry is None:
        _registry = CapsuleRegistry()
    return _registry


def reset_capsule_registry() -> CapsuleRegistry:
    """重置并返回新的注册表实例（用于热重载）。"""
    global _registry
    _registry = CapsuleRegistry()
    return _registry
