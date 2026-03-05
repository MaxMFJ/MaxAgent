"""
v3.2 Traces API — 暴露 task trace 数据，供前端监控/排障使用。

端点：
  GET  /traces                      列出所有 task trace（最近 50 条）
  GET  /traces/{task_id}            获取指定 task 的统计摘要
  GET  /traces/{task_id}/spans      获取指定 task 的原始 spans（分页）
  DELETE /traces/{task_id}          删除指定 task 的 trace 文件
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/traces", tags=["traces"])


def _get_trace_module():
    try:
        from core.trace_logger import (
            list_traces,
            get_trace_summary,
            get_trace_spans,
            delete_trace,
        )
        return list_traces, get_trace_summary, get_trace_spans, delete_trace
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"trace_logger not available: {e}")


@router.get("")
async def list_all_traces(limit: int = Query(50, ge=1, le=200)):
    """列出最近的 trace 记录列表（按 mtime 倒序）。"""
    list_traces, _, _, _ = _get_trace_module()
    return {"traces": list_traces(limit=limit)}


@router.get("/{task_id}")
async def get_task_trace_summary(task_id: str):
    """获取指定 task 的 trace 统计摘要（token、延迟、工具成功率等）。"""
    _, get_trace_summary, _, _ = _get_trace_module()
    summary = get_trace_summary(task_id)
    if not summary.get("exists", False):
        raise HTTPException(status_code=404, detail=f"Trace not found for task_id={task_id}")
    return summary


@router.get("/{task_id}/spans")
async def get_task_spans(
    task_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    span_type: Optional[str] = Query(None, description="llm|tool|step|... 过滤类型"),
):
    """获取指定 task 的原始 span 列表（支持分页与类型过滤）。"""
    _, _, get_trace_spans, _ = _get_trace_module()
    spans = get_trace_spans(task_id, offset=offset, limit=limit, span_type=span_type)
    return {
        "task_id": task_id,
        "offset": offset,
        "count": len(spans),
        "spans": spans,
    }


@router.delete("/{task_id}")
async def delete_task_trace(task_id: str):
    """删除指定 task 的 trace 文件（不可逆）。"""
    _, _, _, delete_trace = _get_trace_module()
    ok = delete_trace(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Trace not found for task_id={task_id}")
    return {"deleted": True, "task_id": task_id}
