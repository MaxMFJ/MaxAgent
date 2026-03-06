"""Health / Status / Connections 路由

v3.2 增强：
  - /health/deep  深度健康检查（LLM 连通性、磁盘/内存、vector DB、工具、agent 状态）
"""
import os
import time
import asyncio
import logging

from fastapi import APIRouter

from app_state import get_server_status, get_llm_client, ENABLE_EVOMAP
from connection_manager import connection_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check():
    llm = get_llm_client()
    evomap_status = "disabled"
    if ENABLE_EVOMAP:
        try:
            from agent.evomap_service import get_evomap_service
            evomap_ok = get_evomap_service()._initialized
            evomap_status = "connected" if evomap_ok else "initializing"
        except Exception:
            pass
    return {
        "status": "healthy",
        "server_status": get_server_status().value,
        "provider": llm.config.provider if llm else None,
        "model": llm.config.model if llm else None,
        "evomap": evomap_status,
    }


@router.get("/health/deep")
async def deep_health_check():
    """
    v3.2 深度健康检查：综合检查各子系统状态。
    返回各项状态及整体 healthy 标志（所有 required 项通过才为 true）。
    """
    checks: dict = {}
    t0 = time.time()

    # ── 1. LLM 连通性（非阻塞探测，超时 5s）─────────────────────────────
    llm = get_llm_client()
    llm_ok = False
    llm_latency_ms: float = 0
    llm_detail = ""
    if llm:
        try:
            t1 = time.time()
            # 发送最小请求探测连通性（max_tokens=1 降低成本）
            result = await asyncio.wait_for(
                llm._client.chat.completions.create(
                    model=llm.config.model,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                ),
                timeout=5.0,
            )
            llm_latency_ms = round((time.time() - t1) * 1000, 1)
            llm_ok = True
            llm_detail = f"provider={llm.config.provider} model={llm.config.model}"
        except asyncio.TimeoutError:
            llm_detail = "timeout(5s)"
        except Exception as e:
            llm_detail = str(e)[:120]
    else:
        llm_detail = "no llm client configured"

    checks["llm"] = {
        "ok": llm_ok,
        "required": True,
        "latency_ms": llm_latency_ms,
        "detail": llm_detail,
    }

    # ── 2. 磁盘空间 ──────────────────────────────────────────────────────
    disk_ok = False
    disk_detail = ""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024 ** 3)
        disk_ok = free_gb > 0.5  # 500 MB 阈值
        disk_detail = f"free={free_gb:.1f}GB total={total / (1024**3):.1f}GB"
    except Exception as e:
        disk_detail = str(e)

    checks["disk"] = {"ok": disk_ok, "required": False, "detail": disk_detail}

    # ── 3. 内存使用 ──────────────────────────────────────────────────────
    mem_ok = False
    mem_detail = ""
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        mem_ok = vm.percent < 95
        mem_detail = (
            f"used={vm.percent:.1f}% "
            f"available={vm.available / (1024**2):.0f}MB "
            f"total={vm.total / (1024**2):.0f}MB"
        )
    except ImportError:
        mem_detail = "psutil not installed (skipped)"
        mem_ok = True  # 无法检测时不阻塞 healthy
    except Exception as e:
        mem_detail = str(e)

    checks["memory"] = {"ok": mem_ok, "required": False, "detail": mem_detail}

    # ── 4. Vector DB（BGE embedding 向量存储）────────────────────────────
    vec_ok = False
    vec_detail = ""
    try:
        from agent.vector_store import get_vector_store
        vs = get_vector_store("__health_probe__")
        vec_ok = vs is not None
        vec_detail = f"type={type(vs).__name__}"
    except Exception as e:
        vec_detail = str(e)[:120]

    checks["vector_db"] = {"ok": vec_ok, "required": False, "detail": vec_detail}

    # ── 5. 工具路由可用性 ─────────────────────────────────────────────────
    tools_ok = False
    tools_detail = ""
    try:
        from tools.router import list_tools  # type: ignore
        tool_list = list_tools()
        tools_ok = len(tool_list) > 0
        tools_detail = f"registered={len(tool_list)}"
    except Exception as e:
        # router 可能没有 list_tools，视为可用
        tools_ok = True
        tools_detail = f"list_tools not available: {e}"

    checks["tools"] = {"ok": tools_ok, "required": False, "detail": tools_detail}

    # ── 6. Task tracker──────────────────────────────────────────────────
    tracker_ok = False
    tracker_detail = ""
    try:
        from app_state import get_task_tracker
        tracker = get_task_tracker()
        stats = tracker.get_stats() if hasattr(tracker, "get_stats") else {}
        tracker_ok = True
        tracker_detail = (
            f"running={stats.get('running', '?')} "
            f"total={stats.get('total', '?')}"
        )
    except Exception as e:
        tracker_detail = str(e)[:120]

    checks["task_tracker"] = {"ok": tracker_ok, "required": False, "detail": tracker_detail}

    # ── 7. Traces 目录 ────────────────────────────────────────────────────
    traces_ok = False
    traces_detail = ""
    try:
        from core.trace_logger import TRACES_DIR, list_traces, _ensure_traces_dir
        _ensure_traces_dir()
        traces_ok = os.path.isdir(TRACES_DIR)
        recent = list_traces(limit=5)
        traces_detail = f"dir_ok={traces_ok} recent_tasks={len(recent)}"
    except Exception as e:
        traces_detail = str(e)[:120]

    checks["traces"] = {"ok": traces_ok, "required": False, "detail": traces_detail}

    # ── 8. EvoMap（可选）─────────────────────────────────────────────────
    if ENABLE_EVOMAP:
        evo_ok = False
        evo_detail = ""
        try:
            from agent.evomap_service import get_evomap_service
            evo_ok = get_evomap_service()._initialized
            evo_detail = "connected" if evo_ok else "initializing"
        except Exception as e:
            evo_detail = str(e)[:80]
        checks["evomap"] = {"ok": evo_ok, "required": False, "detail": evo_detail}

    # ── 汇总 ──────────────────────────────────────────────────────────────
    required_failed = [k for k, v in checks.items() if v.get("required") and not v["ok"]]
    overall_healthy = len(required_failed) == 0
    total_ms = round((time.time() - t0) * 1000, 1)

    return {
        "healthy": overall_healthy,
        "required_failed": required_failed,
        "server_status": get_server_status().value,
        "checks": checks,
        "check_duration_ms": total_ms,
        "ts": time.time(),
    }


@router.get("/server-status")
async def server_status():
    return {"server_status": get_server_status().value}


@router.get("/connections")
async def get_connections():
    return connection_manager.get_stats()
