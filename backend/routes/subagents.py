"""Subagent REST API — 查看活跃子 Agent"""
from typing import Optional

from fastapi import APIRouter

from services.subagent_service import get_subagent_scheduler

router = APIRouter()


@router.get("/subagents")
async def list_active_subagents():
    """查看所有活跃的子 Agent"""
    scheduler = get_subagent_scheduler()
    return {"subagents": scheduler.get_active_subtasks()}


@router.get("/subagents/{task_id}")
async def get_task_subagents(task_id: str):
    """查看指定任务的子 Agent 状态"""
    scheduler = get_subagent_scheduler()
    return {"task_id": task_id, "subagents": scheduler.get_active_subtasks(task_id)}
