"""
ACP Phase 5 — Streaming Route

GET /agent/stream/{task_id}   SSE 流式事件
支持可见性级别过滤: ?visibility=minimal|standard|verbose|debug
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from models.acp_models import ACPEventType, Visibility
from services.acp_streaming import StreamingAdapter
from services.acp_security import (
    CapabilityTokenClaims,
    extract_token_from_header,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["ACP"])


async def _optional_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Optional[CapabilityTokenClaims]:
    raw = extract_token_from_header(authorization)
    if not raw:
        return None
    claims = verify_token(raw)
    if not claims:
        raise HTTPException(401, "Invalid or expired token")
    return claims


@router.get("/stream/{task_id}")
async def stream_task(
    task_id: str,
    visibility: str = Query("standard", description="minimal|standard|verbose|debug"),
    claims: Optional[CapabilityTokenClaims] = Depends(_optional_token),
):
    """
    SSE 流式事件端点。
    实时推送任务执行事件，支持可见性级别过滤。
    """
    # 验证可见性参数
    try:
        vis = Visibility(visibility)
    except ValueError:
        vis = Visibility.STANDARD

    # 验证任务存在
    from routes.agent_tasks import get_task_status, get_task_stream_events
    status = get_task_status(task_id)

    # 也检查 invoke async tasks
    if status is None:
        from routes.agent_invoke import get_async_task_result
        if get_async_task_result(task_id) is None:
            raise HTTPException(404, f"Task not found: {task_id}")

    adapter = StreamingAdapter(task_id=task_id, visibility=vis)

    async def _event_generator():
        """SSE 事件生成器。"""
        last_idx = 0

        while True:
            events = get_task_stream_events(task_id)
            if events is None:
                # 任务不存在或已清理
                break

            # 发送新事件
            while last_idx < len(events):
                raw_event = events[last_idx]
                last_idx += 1
                acp_event = adapter.adapt(raw_event)
                if acp_event:
                    yield adapter.format_sse(acp_event)

            # 检查任务是否已终止
            current_status = get_task_status(task_id)
            if current_status in ("completed", "failed", "cancelled"):
                # 发送最终事件
                if current_status == "completed":
                    final_event = adapter.adapt({"type": "done", "status": current_status})
                elif current_status == "failed":
                    final_event = adapter.adapt({"type": "error", "status": current_status})
                else:
                    final_event = adapter.adapt({"type": "cancelled", "status": current_status})
                if final_event:
                    yield adapter.format_sse(final_event)
                break

            # 轮询间隔
            await asyncio.sleep(0.5)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
