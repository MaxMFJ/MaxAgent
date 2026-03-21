"""
Scheduled Tasks API — 定时/周期任务 CRUD

Endpoints:
  POST   /scheduled-tasks          创建定时任务
  GET    /scheduled-tasks          列出所有定时任务
  GET    /scheduled-tasks/{id}     查询单个定时任务
  POST   /scheduled-tasks/{id}/pause   暂停
  POST   /scheduled-tasks/{id}/resume  恢复
  DELETE /scheduled-tasks/{id}     删除
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


class CreateScheduledTaskRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    trigger_type: str = Field(..., pattern="^(interval|cron)$")
    trigger_config: Dict[str, Any]
    session_id: str = ""


class ScheduledTaskResponse(BaseModel):
    task_id: str
    description: str
    trigger_type: str
    trigger_config: Dict[str, Any]
    status: str
    session_id: str
    created_at: str
    last_run_at: Optional[str]
    next_run_at: Optional[str]
    run_count: int
    last_error: Optional[str]


@router.post("", response_model=ScheduledTaskResponse)
async def create_scheduled_task(req: CreateScheduledTaskRequest):
    svc = ScheduledTaskService.get_instance()

    # 验证 trigger_config
    if req.trigger_type == "interval":
        seconds = req.trigger_config.get("every_seconds")
        if not isinstance(seconds, (int, float)) or seconds < 60:
            raise HTTPException(400, "interval trigger requires every_seconds >= 60")
    elif req.trigger_type == "cron":
        hour = req.trigger_config.get("hour")
        if hour is not None and not (0 <= hour <= 23):
            raise HTTPException(400, "cron hour must be 0-23")
        minute = req.trigger_config.get("minute")
        if minute is not None and not (0 <= minute <= 59):
            raise HTTPException(400, "cron minute must be 0-59")
        weekday = req.trigger_config.get("weekday")
        if weekday is not None and not (0 <= weekday <= 6):
            raise HTTPException(400, "cron weekday must be 0(Mon)-6(Sun)")

    task = svc.create_task(
        description=req.description,
        trigger_type=req.trigger_type,
        trigger_config=req.trigger_config,
        session_id=req.session_id,
    )
    return task.to_dict()


@router.get("", response_model=List[ScheduledTaskResponse])
async def list_scheduled_tasks():
    svc = ScheduledTaskService.get_instance()
    return [t.to_dict() for t in svc.list_tasks()]


@router.get("/{task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(task_id: str):
    svc = ScheduledTaskService.get_instance()
    task = svc.get_task(task_id)
    if not task:
        raise HTTPException(404, "Scheduled task not found")
    return task.to_dict()


@router.post("/{task_id}/pause")
async def pause_scheduled_task(task_id: str):
    svc = ScheduledTaskService.get_instance()
    if not svc.pause_task(task_id):
        raise HTTPException(404, "Scheduled task not found")
    return {"status": "paused", "task_id": task_id}


@router.post("/{task_id}/resume")
async def resume_scheduled_task(task_id: str):
    svc = ScheduledTaskService.get_instance()
    if not svc.resume_task(task_id):
        raise HTTPException(404, "Scheduled task not found")
    return {"status": "active", "task_id": task_id}


@router.delete("/{task_id}")
async def delete_scheduled_task(task_id: str):
    svc = ScheduledTaskService.get_instance()
    if not svc.delete_task(task_id):
        raise HTTPException(404, "Scheduled task not found")
    return {"status": "deleted", "task_id": task_id}
