"""
Runbook Registry — RPA 机器人流程自动化注册中心（单例）

- 启动时从 backend/runbooks/ 目录加载所有 YAML/JSON 文件
- 支持按名称/描述/标签/类别的模糊搜索
- 支持动态导入（用户通过 API 上传）与删除
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# 本地存放 runbook 文件的目录
RUNBOOKS_DIR = Path(__file__).parent.parent / "runbooks"

# 懒加载 PyYAML：如不可用则退化为 JSON-only
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from agent.runbook_models import Runbook


def _load_file(path: Path) -> Optional[dict]:
    """读取单个 YAML/JSON 文件，返回原始 dict 或 None"""
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml") and _YAML_AVAILABLE:
            return _yaml.safe_load(text)
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Failed to load runbook file {path}: {e}")
        return None


def _score_runbook(rb: Runbook, query: str) -> float:
    """简单加权评分：query 词命中 description/name/tags/category 越多分越高"""
    if not query.strip():
        return 1.0
    words = re.split(r"[\s\-_/,]+", query.lower())
    target = " ".join([
        rb.name.lower(), rb.description.lower(),
        " ".join(rb.tags).lower(), rb.category.lower(),
    ])
    hits = sum(1 for w in words if w and w in target)
    return hits / max(len(words), 1)


class RunbookRegistry:
    """RPA Runbook 注册中心（进程内单例）"""

    _instance: Optional["RunbookRegistry"] = None

    def __init__(self):
        self._runbooks: dict[str, Runbook] = {}   # id → Runbook
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "RunbookRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─── 初始化 ──────────────────────────────────────

    def initialize(self) -> None:
        if self._loaded:
            return
        RUNBOOKS_DIR.mkdir(parents=True, exist_ok=True)
        for path in sorted(RUNBOOKS_DIR.iterdir()):
            if path.suffix in (".yaml", ".yml", ".json"):
                raw = _load_file(path)
                if raw and isinstance(raw, dict) and "id" in raw:
                    try:
                        rb = Runbook.from_dict(raw)
                        rb.source = raw.get("source", "local")
                        self._runbooks[rb.id] = rb
                    except Exception as e:
                        logger.warning(f"Invalid runbook in {path}: {e}")
        self._loaded = True
        logger.info(f"RunbookRegistry loaded {len(self._runbooks)} runbooks from {RUNBOOKS_DIR}")

    # ─── 查询 ────────────────────────────────────────

    def list_all(self) -> List[Runbook]:
        return list(self._runbooks.values())

    def get(self, runbook_id: str) -> Optional[Runbook]:
        return self._runbooks.get(runbook_id)

    def find_by_query(self, query: str, limit: int = 5, min_score: float = 0.3) -> List[Runbook]:
        """根据自然语言查询返回最相关的 Runbook 列表"""
        scored = [
            (rb, _score_runbook(rb, query))
            for rb in self._runbooks.values()
        ]
        scored.sort(key=lambda x: -x[1])
        return [rb for rb, score in scored if score >= min_score][:limit]

    def find_by_query_with_scores(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.3,
        categories: Optional[List[str]] = None,
    ) -> List[Tuple[Runbook, float]]:
        """
        根据自然语言查询返回 (Runbook, score) 列表，便于调用方按注入阈值过滤。
        categories: 若非空，仅返回 category 在列表中的 Runbook。
        """
        scored = [
            (rb, _score_runbook(rb, query))
            for rb in self._runbooks.values()
            if categories is None or rb.category in categories
        ]
        scored.sort(key=lambda x: -x[1])
        return [(rb, score) for rb, score in scored if score >= min_score][:limit]

    def find_by_category(self, category: str) -> List[Runbook]:
        return [rb for rb in self._runbooks.values() if rb.category == category]

    def find_by_tag(self, tag: str) -> List[Runbook]:
        return [rb for rb in self._runbooks.values() if tag in rb.tags]

    # ─── 导入 / 删除 ─────────────────────────────────

    def import_runbook(self, data: dict, overwrite: bool = False) -> Runbook:
        """从 dict 导入一个 Runbook，并持久化到磁盘"""
        if "id" not in data:
            raise ValueError("Runbook must have an 'id' field")
        rb_id = data["id"]
        if rb_id in self._runbooks and not overwrite:
            raise ValueError(f"Runbook '{rb_id}' already exists. Use overwrite=True to replace.")

        rb = Runbook.from_dict(data)
        rb.source = data.get("source", "imported")
        self._runbooks[rb_id] = rb
        self._persist_runbook(rb)
        logger.info(f"Imported runbook: {rb_id}")
        return rb

    def _persist_runbook(self, rb: Runbook) -> None:
        RUNBOOKS_DIR.mkdir(parents=True, exist_ok=True)
        path = RUNBOOKS_DIR / f"{rb.id}.json"
        path.write_text(
            json.dumps(rb.to_dict(include_steps=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_runbook(self, runbook_id: str) -> bool:
        if runbook_id not in self._runbooks:
            return False
        del self._runbooks[runbook_id]
        for ext in ("json", "yaml", "yml"):
            path = RUNBOOKS_DIR / f"{runbook_id}.{ext}"
            if path.exists():
                path.unlink()
        logger.info(f"Deleted runbook: {runbook_id}")
        return True

    def record_execution(self, runbook_id: str, session_id: str = "runbook", task_id: str = "") -> None:
        rb = self._runbooks.get(runbook_id)
        if rb:
            rb.execute_count += 1
            rb.last_used = time.time()
        # 广播 RPA 执行事件到监控面板（异步广播，不阻塞调用方）
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                loop.create_task(
                    self._broadcast_runbook_event(runbook_id, rb, session_id, task_id)
                )
        except RuntimeError:
            pass  # 无运行中的事件循环，跳过广播

    @staticmethod
    async def _broadcast_runbook_event(
        runbook_id: str, rb, session_id: str, task_id: str
    ) -> None:
        """异步广播 RPA Runbook 执行事件到监控面板"""
        try:
            from ws_handler import broadcast_monitor_event
            event_task_id = task_id or f"rpa_{runbook_id[:12]}"
            rb_name = rb.name if rb else runbook_id
            rb_category = rb.category if rb else "general"
            await broadcast_monitor_event(
                session_id=session_id,
                task_id=event_task_id,
                event={
                    "type": "runbook_executed",
                    "runbook_id": runbook_id,
                    "runbook_name": rb_name,
                    "runbook_category": rb_category,
                    "execute_count": rb.execute_count if rb else 0,
                },
                task_type="runbook",
                worker_type="main",
                worker_id="main",
            )
        except Exception:
            pass

    # ─── 用于 prompt 注入的简要索引 ──────────────────

    def get_prompt_index(self, limit: int = 20) -> str:
        """返回供 LLM 参考的 Runbook 摘要（简洁形式）"""
        items = sorted(self._runbooks.values(), key=lambda r: -r.execute_count)[:limit]
        if not items:
            return ""
        lines = [f"- {rb.id} [{rb.category}]: {rb.description[:80]}" for rb in items]
        return "\n".join(lines)


# 模块级便捷函数
def get_runbook_registry() -> RunbookRegistry:
    reg = RunbookRegistry.get_instance()
    if not reg._loaded:
        reg.initialize()
    return reg
