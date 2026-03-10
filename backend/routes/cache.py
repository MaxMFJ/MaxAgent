"""
清理缓存 API：清除 traces、task_store、duck_tasks、audit、usage_stats、system_messages、
contexts、execution_guard_metrics 等运行时数据，保留配置文件。
"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter

from paths import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])

# 要清理的目录/文件（相对 DATA_DIR）
CLEANUP_PATHS = [
    "traces",           # trace 日志
    "task_store/checkpoints",  # 任务检查点（含 chat 会话持久化）
    "task_store/metadata",
    "duck_tasks",       # Duck 任务结果
    "audit",            # 审计日志
    "usage_stats",      # 使用统计
    "contexts",        # 服务端 chat 上下文
    "task_cache",      # 幂等任务缓存
    "episodes",        # 情景记忆
]
CLEANUP_FILES = [
    "system_messages.json",
    "execution_guard_metrics.jsonl",
]

# 保留的配置（不清理）
PRESERVE = [
    "config",
    "prompts",
    "agent_config.json",
    "llm_config.json",
    "github_config.json",
    "smtp_config.json",
    "duck_registry.json",
    "duck_eggs.json",
    "signatures.json",
]


def _safe_remove(path: Path, is_dir: bool) -> int:
    """删除文件或目录，返回删除的文件数"""
    count = 0
    try:
        if not path.exists():
            return 0
        if is_dir:
            for f in path.rglob("*"):
                if f.is_file():
                    f.unlink()
                    count += 1
            for d in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if d.is_dir():
                    d.rmdir()
            if path.is_dir():
                path.rmdir()
        else:
            path.unlink()
            count = 1
    except OSError as e:
        logger.warning(f"Failed to remove {path}: {e}")
    return count


@router.post("/clear")
async def clear_cache():
    """
    清理缓存：删除 traces、任务检查点、duck_tasks、audit、usage_stats、
    system_messages、contexts 等运行时数据。保留 config、prompts、LLM 配置等。
    """
    data_dir = Path(DATA_DIR)
    if not data_dir.exists():
        return {"ok": True, "deleted": 0, "message": "数据目录不存在"}

    total = 0

    # 清理目录
    for rel in CLEANUP_PATHS:
        p = data_dir / rel
        n = _safe_remove(p, is_dir=True)
        total += n
        if n > 0:
            logger.info(f"Cleared {rel}: {n} items")

    # 清理单文件
    for name in CLEANUP_FILES:
        p = data_dir / name
        if p.exists():
            try:
                if name == "system_messages.json":
                    # 重置为空数组而非删除，避免服务依赖报错
                    p.write_text("[]", encoding="utf-8")
                else:
                    p.unlink()
                total += 1
            except OSError as e:
                logger.warning(f"Failed to clear {name}: {e}")

    return {
        "ok": True,
        "deleted": total,
        "message": f"已清理 {total} 项缓存数据，配置文件已保留",
    }
