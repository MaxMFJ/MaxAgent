"""
跨会话持久记忆系统 — 从 Episode 中提取可复用事实，经验积累

借鉴 DeerFlow Memory Middleware:
  - 每次任务完成后，抽取关键事实（工具偏好、路径规律、错误教训）
  - 事实以 FactEntry 存储，按类型索引
  - 新任务开始时自动检索相关事实注入 prompt

层次:
  ┌───────────────────────┐
  │   Episodic Memory     │  ← 完整任务记录（已有）
  │   (episodes/*.json)   │
  └───────┬───────────────┘
          │  extract_facts()
  ┌───────▼───────────────┐
  │  Persistent Factbase  │  ← 提炼的可复用事实（新增）
  │  (factbase.json)      │
  └───────┬───────────────┘
          │  recall()
  ┌───────▼───────────────┐
  │  Prompt Injection     │  ← 注入到下一任务的 context_str
  └───────────────────────┘
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── 事实类型枚举 ──────────────────────────────────────────────────

class FactType:
    """事实分类"""
    TOOL_PREFERENCE = "tool_preference"       # 工具偏好和最佳实践
    ERROR_LESSON = "error_lesson"             # 错误教训（避免重蹈覆辙）
    PATH_PATTERN = "path_pattern"             # 文件/目录路径规律
    STRATEGY_PATTERN = "strategy_pattern"     # 成功策略模式
    ENVIRONMENT_FACT = "environment_fact"     # 环境信息（系统、权限等）
    USER_PREFERENCE = "user_preference"       # 用户偏好（推断而来）


# ─── 事实条目 ──────────────────────────────────────────────────────

@dataclass
class FactEntry:
    """一条可复用事实"""
    fact_id: str
    fact_type: str                     # FactType 值
    content: str                       # 事实内容（自然语言）
    source_episode_id: str             # 来源 Episode
    confidence: float = 0.8            # 置信度 0~1
    use_count: int = 0                 # 被召回使用的次数
    created_at: str = ""               # ISO 时间戳
    last_used_at: str = ""             # 上次使用时间
    tags: List[str] = field(default_factory=list)  # 关键词标签

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FactEntry":
        return cls(
            fact_id=data.get("fact_id", ""),
            fact_type=data.get("fact_type", FactType.STRATEGY_PATTERN),
            content=data.get("content", ""),
            source_episode_id=data.get("source_episode_id", ""),
            confidence=float(data.get("confidence", 0.8)),
            use_count=int(data.get("use_count", 0)),
            created_at=data.get("created_at", ""),
            last_used_at=data.get("last_used_at", ""),
            tags=data.get("tags", []),
        )


# ─── 事实提取器 ──────────────────────────────────────────────────

class FactExtractor:
    """
    从 Episode 的 action_log 中提取可复用事实。
    基于规则的轻量提取器（不依赖 LLM）。
    """

    @staticmethod
    def extract(episode_id: str, task_description: str,
                action_log: List[Dict], success: bool,
                result: str = "") -> List[FactEntry]:
        """从单个 Episode 提取事实"""
        facts: List[FactEntry] = []
        now = datetime.now().isoformat()

        # 1. 成功策略提取
        if success and action_log:
            tool_sequence = [
                log.get("action_type", "") for log in action_log
                if log.get("success", False)
            ]
            if len(tool_sequence) >= 2:
                # 提取成功工具序列
                unique_tools = list(dict.fromkeys(tool_sequence))  # 去重保序
                facts.append(FactEntry(
                    fact_id=f"strat_{episode_id}_{int(time.time())}",
                    fact_type=FactType.STRATEGY_PATTERN,
                    content=f"任务「{task_description[:60]}」的成功工具序列：{' → '.join(unique_tools[:8])}",
                    source_episode_id=episode_id,
                    confidence=0.7 + min(len(tool_sequence) / 20.0, 0.3),
                    created_at=now,
                    tags=_extract_keywords(task_description),
                ))

        # 2. 错误教训提取
        errors_seen: Dict[str, int] = {}
        for log in action_log:
            error = log.get("error")
            if error and isinstance(error, str) and len(error) > 10:
                at = log.get("action_type", "unknown")
                key = f"{at}:{error[:80]}"
                errors_seen[key] = errors_seen.get(key, 0) + 1

        for key, count in errors_seen.items():
            if count >= 2:  # 同一错误出现 2 次以上才值得纪录
                at, err_msg = key.split(":", 1)
                facts.append(FactEntry(
                    fact_id=f"err_{episode_id}_{hash(key) & 0xFFFFFF:06x}",
                    fact_type=FactType.ERROR_LESSON,
                    content=f"在执行 {at} 时反复遇到错误（{count}次）：{err_msg}。应避免此模式。",
                    source_episode_id=episode_id,
                    confidence=min(0.5 + count * 0.1, 0.95),
                    created_at=now,
                    tags=[at, "error"],
                ))

        # 3. 文件路径规律
        paths_used = set()
        for log in action_log:
            params = log.get("params") or {}
            for key in ("path", "file_path", "target", "directory"):
                val = params.get(key, "")
                if val and isinstance(val, str) and "/" in val:
                    # 提取目录部分
                    dir_part = os.path.dirname(val)
                    if dir_part and len(dir_part) > 3:
                        paths_used.add(dir_part)

        if paths_used and len(paths_used) <= 5:
            facts.append(FactEntry(
                fact_id=f"path_{episode_id}_{int(time.time())}",
                fact_type=FactType.PATH_PATTERN,
                content=f"任务常用目录：{', '.join(sorted(paths_used)[:5])}",
                source_episode_id=episode_id,
                confidence=0.6,
                created_at=now,
                tags=list(paths_used)[:3],
            ))

        # 4. 工具偏好
        if success:
            tool_counts: Dict[str, int] = {}
            for log in action_log:
                at = log.get("action_type", "")
                if at and log.get("success", False):
                    tool_counts[at] = tool_counts.get(at, 0) + 1
            if tool_counts:
                top_tool = max(tool_counts, key=tool_counts.get)  # type: ignore
                if tool_counts[top_tool] >= 3:
                    facts.append(FactEntry(
                        fact_id=f"tool_{episode_id}_{int(time.time())}",
                        fact_type=FactType.TOOL_PREFERENCE,
                        content=f"完成类似任务时，{top_tool} 是最常用的工具（使用{tool_counts[top_tool]}次）。",
                        source_episode_id=episode_id,
                        confidence=0.7,
                        created_at=now,
                        tags=[top_tool] + _extract_keywords(task_description)[:3],
                    ))

        return facts


# ─── 持久化事实库 ──────────────────────────────────────────────────

class PersistentFactbase:
    """
    跨会话事实库 — JSON 文件存储。
    按 fact_type 索引，支持关键词检索。
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = os.path.join(
                os.path.dirname(__file__),
                "..", "data", "factbase.json"
            )
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._facts: Dict[str, FactEntry] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    fact = FactEntry.from_dict(item)
                    self._facts[fact.fact_id] = fact
                logger.info(f"Factbase loaded: {len(self._facts)} facts")
            except Exception as e:
                logger.warning(f"Factbase load failed: {e}")

    def _save(self):
        try:
            data = [f.to_dict() for f in self._facts.values()]
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Factbase save failed: {e}")

    def add_facts(self, facts: List[FactEntry]) -> int:
        """添加事实（去重：相同 content 不重复添加）"""
        added = 0
        existing_contents = {f.content for f in self._facts.values()}
        for fact in facts:
            if fact.content not in existing_contents:
                self._facts[fact.fact_id] = fact
                existing_contents.add(fact.content)
                added += 1
        if added:
            self._trim()
            self._save()
            logger.info(f"Factbase: added {added} new facts (total: {len(self._facts)})")
        return added

    def recall(self, task_description: str, top_k: int = 5,
               fact_types: Optional[List[str]] = None) -> List[FactEntry]:
        """
        根据任务描述召回相关事实。
        使用关键词 Jaccard 相似度 + 使用频率加权。
        """
        task_words = set(task_description.lower().split())
        if not task_words:
            return []

        candidates = list(self._facts.values())
        if fact_types:
            candidates = [f for f in candidates if f.fact_type in fact_types]

        scored = []
        for fact in candidates:
            # 标签匹配
            fact_words = set(w.lower() for w in fact.tags)
            fact_words |= set(fact.content.lower().split())
            intersection = len(task_words & fact_words)
            union = len(task_words | fact_words)
            similarity = intersection / union if union else 0.0

            # 使用频率衰减（高频事实权重降低，鼓励探索）
            freq_decay = 1.0 / (1 + fact.use_count * 0.1)

            # 置信度加权
            score = similarity * fact.confidence * freq_decay
            if score > 0.01:
                scored.append((score, fact))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [f for _, f in scored[:top_k]]

        # 更新使用计数
        now = datetime.now().isoformat()
        for fact in results:
            fact.use_count += 1
            fact.last_used_at = now
        if results:
            self._save()

        return results

    def recall_for_prompt(self, task_description: str, max_chars: int = 1000) -> str:
        """
        召回相关事实并格式化为可注入 prompt 的文本。
        """
        facts = self.recall(task_description, top_k=5)
        if not facts:
            return ""

        lines = ["【历史经验参考】"]
        total_len = 20  # header length
        for i, fact in enumerate(facts, 1):
            line = f"{i}. [{fact.fact_type}] {fact.content}"
            if total_len + len(line) > max_chars:
                break
            lines.append(line)
            total_len += len(line) + 1

        return "\n".join(lines)

    def get_statistics(self) -> Dict[str, Any]:
        """统计信息"""
        type_counts: Dict[str, int] = {}
        for fact in self._facts.values():
            type_counts[fact.fact_type] = type_counts.get(fact.fact_type, 0) + 1
        return {
            "total_facts": len(self._facts),
            "by_type": type_counts,
            "avg_confidence": (
                sum(f.confidence for f in self._facts.values()) / len(self._facts)
                if self._facts else 0.0
            ),
        }

    def _trim(self, max_facts: int = 500):
        """保留最新/最高置信度的事实"""
        if len(self._facts) <= max_facts:
            return
        # 按置信度 × 新近度排序，保留 top max_facts
        sorted_facts = sorted(
            self._facts.values(),
            key=lambda f: f.confidence * (1 if not f.created_at else 1.0),
            reverse=True,
        )
        self._facts = {f.fact_id: f for f in sorted_facts[:max_facts]}


# ─── 辅助函数 ──────────────────────────────────────────────────────

def _extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """从文本中提取关键词（简单切分 + 停词过滤）"""
    stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不",
                  "人", "都", "一", "个", "上", "也", "到", "说", "要",
                  "a", "the", "is", "in", "to", "and", "of", "for", "it",
                  "with", "as", "on", "at", "by", "from", "this", "that"}
    words = text.lower().replace("，", " ").replace("。", " ").split()
    keywords = [w for w in words if len(w) > 1 and w not in stop_words]
    return keywords[:max_keywords]


# ─── 单例 ──────────────────────────────────────────────────────────

_factbase_instance: Optional[PersistentFactbase] = None


def get_factbase() -> PersistentFactbase:
    global _factbase_instance
    if _factbase_instance is None:
        _factbase_instance = PersistentFactbase()
    return _factbase_instance
