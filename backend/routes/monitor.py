"""
Monitor 路由 - 为前端监控仪表板提供 HTTP API
提供：执行历史记录、统计摘要数据
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monitor")

DATA_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "data"))


def _get_episodes_dir() -> Path:
    """获取 episodes 存储目录"""
    d = DATA_DIR / "episodes"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/episodes")
async def get_episodes(count: int = Query(default=20, ge=1, le=100)):
    """
    获取最近 N 条自主任务执行记录（Episode）
    按创建时间倒序，每条返回摘要字段（不含向量嵌入）
    """
    episodes_dir = _get_episodes_dir()
    # 兼容 ep_*.json 与 task_id.json（自主任务完成时保存，task_id 为 8 位 UUID）
    episode_files = sorted(
        [f for f in episodes_dir.glob("*.json") if f.name != "index.json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )[:count]

    results = []
    for fp in episode_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 只返回摘要字段，不含 action_log 详情和向量嵌入
            action_log = data.get("action_log", [])
            tools_used = list({
                step.get("tool_name") or step.get("action_type", "")
                for step in action_log
                if step.get("tool_name") or step.get("action_type")
            })
            results.append({
                "episode_id": data.get("episode_id", fp.stem),
                "task_description": data.get("task_description", ""),
                "success": data.get("success", False),
                "total_actions": data.get("total_actions", 0),
                "total_iterations": data.get("total_iterations", 0),
                "execution_time_ms": data.get("execution_time_ms", 0),
                "token_usage": data.get("token_usage", {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }),
                "tools_used": tools_used,
                "created_at": data.get("created_at", ""),
                "result": data.get("result", ""),
            })
        except Exception as e:
            logger.warning(f"Failed to load episode {fp.name}: {e}")

    return {"episodes": results, "total": len(results)}


@router.get("/statistics")
async def get_execution_statistics():
    """
    统计所有 episode 的聚合指标：
    - 总任务数、成功率、平均迭代次数、平均 Token 消耗
    - 工具使用频率排行（前 10）
    - 近 7 天每日成功/失败数
    """
    episodes_dir = _get_episodes_dir()
    all_files = [f for f in episodes_dir.glob("*.json") if f.name != "index.json"]

    total = 0
    success_count = 0
    total_iterations = 0
    total_tokens = 0
    tool_counts: dict = {}

    for fp in all_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            total += 1
            if data.get("success", False):
                success_count += 1
            total_iterations += data.get("total_iterations", 0)
            total_tokens += data.get("token_usage", {}).get("total_tokens", 0)

            action_log = data.get("action_log", [])
            for step in action_log:
                tool = step.get("tool_name") or step.get("action_type", "")
                if tool:
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1
        except Exception:
            pass

    success_rate = round(success_count / total, 4) if total > 0 else 0.0
    avg_iterations = round(total_iterations / total, 2) if total > 0 else 0.0
    avg_tokens = round(total_tokens / total, 0) if total > 0 else 0.0

    # 工具使用排行（前10）
    tool_ranking = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_tasks": total,
        "success_count": success_count,
        "success_rate": success_rate,
        "avg_iterations": avg_iterations,
        "avg_tokens_per_task": int(avg_tokens),
        "tool_ranking": [{"tool": t, "count": c} for t, c in tool_ranking],
    }
