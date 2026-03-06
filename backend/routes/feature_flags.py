"""FeatureFlag REST API — 查询、热更新、重置"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.feature_flag_service import get_all_flags, update_flag, reset_all_flags

router = APIRouter()


class FlagUpdate(BaseModel):
    name: str
    value: object  # bool / int / float


@router.get("/feature-flags")
async def list_feature_flags():
    """返回所有 FeatureFlag 当前值、默认值、来源"""
    return {"flags": get_all_flags()}


@router.patch("/feature-flags")
async def patch_feature_flag(update: FlagUpdate):
    """热更新指定 Flag（不需重启）"""
    result = update_flag(update.name, update.value)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Flag '{update.name}' not found")
    return result


@router.post("/feature-flags/reset")
async def reset_feature_flags():
    """重置所有 Flag 为默认值"""
    count = reset_all_flags()
    return {"status": "reset", "count": count}
