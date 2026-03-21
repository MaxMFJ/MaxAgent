"""
Remote Worker API — Duck Runtime v3.0

HTTP endpoints for remote worker nodes (RWN) to interact
with the Runtime Authority Node (RAN).

Endpoints:
  POST /workers/register   — Register a remote worker
  POST /workers/pull       — Pull a task from ready queue
  POST /workers/heartbeat  — Refresh heartbeat / extend lease
  POST /workers/complete   — Report task completion
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workers", tags=["workers"])


# ─── Auth Dependency ─────────────────────────────────

def _verify_token(authorization: Optional[str] = Header(None)):
    """Validate Bearer token from Authorization header"""
    from services.remote_pull_protocol import validate_worker_token

    if authorization is None:
        token = ""
    elif authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization

    if not validate_worker_token(token):
        raise HTTPException(status_code=401, detail="Invalid worker token")


# ─── Request/Response Models ─────────────────────────

class RegisterRequest(BaseModel):
    worker_id: str
    duck_type: str
    capabilities: List[str] = Field(default_factory=list)
    version: str = "1.0"


class PullRequest(BaseModel):
    worker_id: str
    duck_type: str


class HeartbeatRequest(BaseModel):
    worker_id: str
    running_task_id: Optional[str] = None


class CompleteRequest(BaseModel):
    worker_id: str
    task_id: str
    result: Any = None
    status: str = "completed"


# ─── Endpoints ───────────────────────────────────────

@router.post("/register")
async def register_worker(
    req: RegisterRequest,
    authorization: Optional[str] = Header(None),
):
    """Register a remote worker node"""
    _verify_token(authorization)

    try:
        from services.remote_pull_protocol import register_worker as do_register
        return await do_register(
            worker_id=req.worker_id,
            duck_type=req.duck_type,
            capabilities=req.capabilities,
            version=req.version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pull")
async def pull_task(
    req: PullRequest,
    response: Response,
    authorization: Optional[str] = Header(None),
):
    """Pull a task from the ready queue"""
    _verify_token(authorization)

    try:
        from services.remote_pull_protocol import pull_task as do_pull
        result = await do_pull(
            worker_id=req.worker_id,
            duck_type=req.duck_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        response.status_code = 204
        return None

    return result


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    authorization: Optional[str] = Header(None),
):
    """Refresh worker heartbeat and optionally extend task lease"""
    _verify_token(authorization)

    try:
        from services.remote_pull_protocol import worker_heartbeat
        return await worker_heartbeat(
            worker_id=req.worker_id,
            running_task_id=req.running_task_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    authorization: Optional[str] = Header(None),
):
    """Report task completion"""
    _verify_token(authorization)

    try:
        from services.remote_pull_protocol import complete_task as do_complete
        return await do_complete(
            worker_id=req.worker_id,
            task_id=req.task_id,
            result=req.result,
            status=req.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
