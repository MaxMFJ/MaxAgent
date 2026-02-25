"""认证相关路由"""
from fastapi import APIRouter

from auth import AUTH_ENABLED, AUTH_TOKEN, generate_auth_token, set_auth

router = APIRouter()


@router.get("/auth/status")
async def auth_status():
    return {
        "auth_enabled": AUTH_ENABLED,
        "has_token": AUTH_TOKEN is not None,
    }


@router.post("/auth/generate-token")
async def generate_token():
    token = generate_auth_token()
    set_auth(enabled=True, token=token)
    return {
        "token": token,
        "message": "Token generated. Share this with your iOS device.",
    }


@router.post("/auth/disable")
async def disable_auth():
    set_auth(enabled=False)
    return {"message": "Authentication disabled"}
