"""
/context 查询路由 — v3.4
类 Claude Code 风格的上下文可视化：展示当前会话状态、Token用量、文件变更、
可用工具、活动任务、快照、模型路由信息等。
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: gather context snapshot
# ---------------------------------------------------------------------------

def _gather_context(session_id: Optional[str] = None) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}

    # ── 1. Session / conversation context ──────────────────────────────────
    try:
        from agent.context_manager import context_manager
        if session_id:
            conv = context_manager.get_or_create(session_id)
            msg_count = len(conv.recent_messages)
            # rough token estimate: 1 token ≈ 4 chars
            raw_text = " ".join(
                m.get("content", "") if isinstance(m.get("content"), str) else ""
                for m in conv.recent_messages
            )
            estimated_tokens = len(raw_text) // 4
            ctx["conversation"] = {
                "session_id": session_id,
                "message_count": msg_count,
                "estimated_tokens": estimated_tokens,
                "max_context_tokens": conv.max_context_tokens,
                "task_tier": conv._current_task_tier,
                "created_files": conv.created_files,
            }
        else:
            # Summarise all active sessions
            sessions = []
            for sid, conv in context_manager.sessions.items():
                sessions.append({
                    "session_id": sid,
                    "message_count": len(conv.recent_messages),
                    "created_files_count": len(conv.created_files),
                })
            ctx["active_sessions"] = sessions
    except Exception as e:
        ctx["conversation_error"] = str(e)

    # ── 2. Active tasks (TaskTracker) ──────────────────────────────────────
    try:
        from app_state import get_task_tracker
        tracker = get_task_tracker()
        if tracker and hasattr(tracker, "_tasks"):
            active = [
                {
                    "task_id": tid,
                    "session_id": t.session_id,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "description": getattr(t, "task_description", "")[:80],
                    "elapsed_s": round(time.time() - t.started_at, 1) if hasattr(t, "started_at") else 0,
                }
                for tid, t in tracker._tasks.items()
            ]
            ctx["active_tasks"] = active
    except Exception:
        ctx["active_tasks"] = []

    # ── 3. Available tools ─────────────────────────────────────────────────
    try:
        from tools.registry import get_tool_registry
        registry = get_tool_registry()
        tools = list(registry.tools.keys()) if hasattr(registry, "tools") else []
        ctx["available_tools"] = tools
    except Exception:
        ctx["available_tools"] = []

    # ── 4. MCP servers & tools ────────────────────────────────────────────
    try:
        from agent.mcp_client import get_mcp_manager
        mgr = get_mcp_manager()
        ctx["mcp"] = {
            "servers": mgr.server_status(),
            "tool_count": sum(len(c.tools) for c in mgr._connections.values()),
        }
    except Exception:
        ctx["mcp"] = {"servers": [], "tool_count": 0}

    # ── 5. Recent snapshots ────────────────────────────────────────────────
    try:
        from agent.snapshot_manager import get_snapshot_manager
        snaps = get_snapshot_manager().list_snapshots(
            session_id=session_id,
            limit=10,
        )
        ctx["snapshots"] = [
            {
                "snapshot_id": s["snapshot_id"],
                "operation": s["operation"],
                "path": s["path"],
                "applied": s["applied"],
                "timestamp": s["timestamp"],
            }
            for s in snaps
        ]
    except Exception:
        ctx["snapshots"] = []

    # ── 6. Model routing / selector stats ─────────────────────────────────
    try:
        from agent.model_selector import get_model_selector
        sel = get_model_selector()
        stats = sel.get_statistics()
        ctx["model_routing"] = {
            "stats": {k: v for k, v in stats.items() if k != "strategy"},
            "tier_configs": sel.get_all_tier_configs(),
        }
    except Exception as e:
        ctx["model_routing"] = {"error": str(e)}

    # ── 7. Phase stats for latest task ─────────────────────────────────────
    try:
        from app_state import get_autonomous_agent
        agent = get_autonomous_agent()
        if agent and hasattr(agent, "_phase_tracker"):
            ctx["phase_stats"] = agent._phase_tracker.stats()
    except Exception:
        pass

    # ── 8. Memory / vector store status ───────────────────────────────────
    try:
        from agent.vector_store import _vector_stores
        ctx["memory"] = {
            "sessions": len(_vector_stores),
            "items_by_session": {sid: len(vs.items) for sid, vs in _vector_stores.items()},
        }
    except Exception:
        ctx["memory"] = {}

    # ── 9. Feature flags ───────────────────────────────────────────────────
    try:
        from app_state import (
            ENABLE_HITL, ENABLE_AUDIT_LOG, ENABLE_SESSION_RESUME,
            ENABLE_SUBAGENT, ENABLE_IDEMPOTENT_TASKS, ENABLE_EVOMAP,
        )
        ctx["feature_flags"] = {
            "ENABLE_HITL": ENABLE_HITL,
            "ENABLE_AUDIT_LOG": ENABLE_AUDIT_LOG,
            "ENABLE_SESSION_RESUME": ENABLE_SESSION_RESUME,
            "ENABLE_SUBAGENT": ENABLE_SUBAGENT,
            "ENABLE_IDEMPOTENT_TASKS": ENABLE_IDEMPOTENT_TASKS,
            "ENABLE_EVOMAP": ENABLE_EVOMAP,
        }
    except Exception:
        ctx["feature_flags"] = {}

    ctx["generated_at"] = time.time()
    return ctx


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/context")
async def get_context(session_id: Optional[str] = Query(None, description="指定会话 ID 以获取会话级详情")):
    """
    返回当前 Agent 运行时的完整上下文快照：
    - 会话消息数 / Token 估算
    - 活动任务
    - 可用工具（内置 + MCP）
    - 最近文件快照
    - 模型路由配置与统计
    - 执行阶段统计（Gather / Act / Verify）
    - 向量记忆状态
    - Feature Flags
    """
    return _gather_context(session_id=session_id)


@router.get("/context/tokens")
async def get_token_usage(session_id: str = Query(..., description="会话 ID")):
    """快速查询单个会话的 Token 使用情况。"""
    try:
        from agent.context_manager import context_manager
        conv = context_manager.get_or_create(session_id)
        raw_text = " ".join(
            m.get("content", "") if isinstance(m.get("content"), str) else ""
            for m in conv.recent_messages
        )
        estimated_tokens = len(raw_text) // 4
        return {
            "session_id": session_id,
            "message_count": len(conv.recent_messages),
            "estimated_tokens": estimated_tokens,
            "max_context_tokens": conv.max_context_tokens,
            "usage_pct": round(estimated_tokens / max(1, conv.max_context_tokens) * 100, 1),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/context/files")
async def get_session_files(session_id: str = Query(..., description="会话 ID")):
    """列出本会话中已创建/修改的文件及其当前状态。"""
    try:
        from agent.context_manager import context_manager
        conv = context_manager.get_or_create(session_id)
        files = []
        for path in conv.created_files:
            info: Dict[str, Any] = {"path": path}
            if os.path.exists(path):
                stat = os.stat(path)
                info["exists"] = True
                info["size"] = stat.st_size
                info["modified"] = stat.st_mtime
            else:
                info["exists"] = False
            files.append(info)
        return {"session_id": session_id, "files": files, "total": len(files)}
    except Exception as e:
        return {"error": str(e)}
