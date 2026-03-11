"""录制回放 API — 管理操作录制、查询、回放"""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from agent.action_recorder import get_action_recorder

router = APIRouter(prefix="/recordings", tags=["recordings"])


class StartRecordingRequest(BaseModel):
    session_id: str = "default"
    name: str = ""
    description: str = ""
    tags: Optional[List[str]] = None


class RecordActionRequest(BaseModel):
    session_id: str = "default"
    tool: str = ""
    action: str = ""
    parameters: dict = {}


class ReplayRequest(BaseModel):
    speed: float = 1.0
    dry_run: bool = False


@router.post("/start")
async def start_recording(body: StartRecordingRequest):
    """开始新的录制"""
    rec = get_action_recorder()
    rec_id = rec.start_recording(
        session_id=body.session_id,
        name=body.name,
        description=body.description,
        tags=body.tags,
    )
    return {"ok": True, "recording_id": rec_id}


@router.post("/stop")
async def stop_recording(session_id: str = "default"):
    """停止录制并保存"""
    rec = get_action_recorder()
    recording = rec.stop_recording(session_id)
    if not recording:
        return {"ok": False, "error": "没有进行中的录制"}
    return {"ok": True, "recording": recording.to_dict()}


@router.post("/action")
async def record_action(body: RecordActionRequest):
    """手动记录一条操作（调试用）"""
    rec = get_action_recorder()
    ok = rec.record_action(
        session_id=body.session_id,
        tool=body.tool,
        action=body.action,
        parameters=body.parameters,
    )
    if not ok:
        return {"ok": False, "error": "没有进行中的录制"}
    return {"ok": True}


@router.get("/status")
async def recording_status(session_id: str = "default"):
    """查询当前录制状态"""
    rec = get_action_recorder()
    active = rec.get_active_recording(session_id)
    if not active:
        return {"recording": False}
    return {
        "recording": True,
        "recording_id": active.id,
        "name": active.name,
        "action_count": len(active.actions),
    }


@router.get("/list")
async def list_recordings():
    """列出所有已保存的录制"""
    rec = get_action_recorder()
    return {"recordings": rec.list_recordings()}


@router.get("/{recording_id}")
async def get_recording(recording_id: str):
    """获取录制详情"""
    rec = get_action_recorder()
    recording = rec.get_recording(recording_id)
    if not recording:
        return {"ok": False, "error": "录制不存在"}
    return {"ok": True, "recording": recording.to_dict()}


@router.delete("/{recording_id}")
async def delete_recording(recording_id: str):
    """删除录制"""
    rec = get_action_recorder()
    ok = rec.delete_recording(recording_id)
    return {"ok": ok}


@router.post("/{recording_id}/replay")
async def replay_recording(recording_id: str, body: ReplayRequest):
    """
    回放一条录制。
    dry_run=true 时仅返回操作列表，不实际执行。
    """
    from tools.router import execute_tool

    rec = get_action_recorder()

    async def tool_executor(tool_name: str, **params):
        return await execute_tool(tool_name, params)

    result = await rec.replay(
        recording_id=recording_id,
        tool_executor=tool_executor,
        speed=body.speed,
        dry_run=body.dry_run,
    )
    return result
