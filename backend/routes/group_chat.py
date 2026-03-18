"""
Group Chat REST API —— 群聊列表 / 详情 / 取消
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.group_chat_service import get_group_chat_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/group-chat", tags=["group-chat"])


@router.get("/list")
async def list_groups(session_id: str = Query(..., description="session ID")):
    """列出某 session 下所有群聊（简要信息）"""
    svc = get_group_chat_service()
    groups = await svc.list_groups(session_id)
    return {"groups": [g.to_brief() for g in groups]}


@router.get("/{group_id}")
async def get_group(group_id: str):
    """获取群聊完整信息（含所有消息）"""
    svc = get_group_chat_service()
    gc = await svc.get_group(group_id)
    if not gc:
        raise HTTPException(status_code=404, detail="群聊不存在")
    return gc.to_dict()


@router.get("/{group_id}/messages")
async def get_messages(
    group_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """分页获取群聊消息"""
    svc = get_group_chat_service()
    gc = await svc.get_group(group_id)
    if not gc:
        raise HTTPException(status_code=404, detail="群聊不存在")
    msgs = gc.messages[offset: offset + limit]
    return {
        "messages": [m.to_dict() for m in msgs],
        "total": len(gc.messages),
        "offset": offset,
    }


@router.post("/{group_id}/cancel")
async def cancel_group(group_id: str):
    """取消群聊（用户操作）"""
    svc = get_group_chat_service()
    gc = await svc.get_group(group_id)
    if not gc:
        raise HTTPException(status_code=404, detail="群聊不存在")
    await svc.cancel_group(group_id)
    return {"status": "cancelled"}


@router.delete("/{group_id}")
async def delete_group(group_id: str):
    """永久删除群聊（用户主动操作，不可恢复）"""
    svc = get_group_chat_service()
    deleted = await svc.delete_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="群聊不存在")
    return {"status": "deleted"}
