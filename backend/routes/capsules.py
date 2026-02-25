"""Capsule 管理路由"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class CapsuleExecuteRequest(BaseModel):
    inputs: Optional[Dict[str, Any]] = None


@router.get("/capsules")
async def capsules_list():
    try:
        from agent.capsule_registry import get_capsule_registry
        reg = get_capsule_registry()
        caps = reg.list_capsules()
        return {"count": len(caps), "capsules": [c.to_dict() for c in caps]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capsules/find")
async def capsules_find(task: str):
    try:
        from agent.capsule_registry import get_capsule_registry
        reg = get_capsule_registry()
        caps = reg.find_capsule_by_task(task)
        return {"count": len(caps), "capsules": [c.to_dict() for c in caps]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capsules/{capsule_id}")
async def capsules_get(capsule_id: str):
    try:
        from agent.capsule_registry import get_capsule_registry
        reg = get_capsule_registry()
        cap = reg.get_capsule(capsule_id)
        if not cap:
            raise HTTPException(status_code=404, detail="Capsule not found")
        return cap.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capsules/{capsule_id}/execute")
async def capsules_execute(capsule_id: str, body: CapsuleExecuteRequest):
    try:
        from agent.capsule_registry import get_capsule_registry
        from agent.capsule_executor import execute_capsule
        reg = get_capsule_registry()
        cap = reg.get_capsule(capsule_id)
        if not cap:
            raise HTTPException(status_code=404, detail="Capsule not found")
        result = await execute_capsule(cap, body.inputs or {})
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
