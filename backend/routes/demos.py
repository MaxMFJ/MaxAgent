"""
人工演示 (Human Demo) API — 录制、管理、学习、审批

端点:
  POST /demos/start       开始录制
  POST /demos/stop        停止录制
  POST /demos/event       手动追加事件
  GET  /demos/status      录制状态
  GET  /demos/list        列出所有演示
  GET  /demos/{demo_id}   查看详情
  DELETE /demos/{demo_id} 删除
  POST /demos/{demo_id}/compress  触发步骤压缩
  POST /demos/{demo_id}/learn     触发 LLM 学习
  POST /demos/{demo_id}/approve   审批 Capsule → 注册
  GET  /demos/{demo_id}/capsule   查看生成的 Capsule
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/demos", tags=["human-demos"])


# ── 请求模型 ──────────────────────────────────────────

class StartDemoRequest(BaseModel):
    session_id: str = "default"
    task_description: str = ""
    tags: Optional[List[str]] = None


class StopDemoRequest(BaseModel):
    session_id: str = "default"


class AddEventRequest(BaseModel):
    session_id: str = "default"
    event_type: str = ""
    data: Dict[str, Any] = {}


class LearnRequest(BaseModel):
    auto_approve: bool = False


# ── 端点 ──────────────────────────────────────────────

@router.post("/start")
async def start_demo(body: StartDemoRequest):
    """开始录制人工演示"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    demo_id = rec.start(
        session_id=body.session_id,
        task_description=body.task_description,
        tags=body.tags,
    )
    return {"ok": True, "demo_id": demo_id}


@router.post("/stop")
async def stop_demo(body: StopDemoRequest):
    """停止录制并保存"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    session = rec.stop(body.session_id)
    if not session:
        return {"ok": False, "error": "没有进行中的演示录制"}

    # 自动执行步骤压缩
    from agent.demo_step_compressor import compress_demo_steps
    compress_demo_steps(session)
    rec.save_session(session)

    return {"ok": True, "demo": session.to_summary()}


@router.post("/event")
async def add_event(body: AddEventRequest):
    """手动追加事件（API/前端用）"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    ok = rec.add_event(
        session_id=body.session_id,
        event_type=body.event_type,
        data=body.data,
    )
    if not ok:
        return {"ok": False, "error": "没有进行中的演示录制"}
    return {"ok": True}


@router.get("/status")
async def demo_status(session_id: str = "default"):
    """查询当前录制状态"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    active = rec.get_active(session_id)
    if not active:
        return {"recording": False}
    return {
        "recording": True,
        "demo_id": active.id,
        "task_description": active.task_description,
        "event_count": len(active.events),
        "step_count": len(active.steps),
    }


@router.get("/list")
async def list_demos():
    """列出所有已保存的演示"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    return {"demos": rec.list_demos()}


@router.get("/{demo_id}")
async def get_demo(demo_id: str):
    """获取演示详情"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    session = rec.load(demo_id)
    if not session:
        return {"ok": False, "error": "演示不存在"}
    return {"ok": True, "demo": session.to_dict()}


@router.delete("/{demo_id}")
async def delete_demo(demo_id: str):
    """删除演示"""
    from agent.human_demo_recorder import get_human_demo_recorder
    rec = get_human_demo_recorder()
    ok = rec.delete_demo(demo_id)
    return {"ok": ok}


@router.post("/{demo_id}/compress")
async def compress_demo(demo_id: str):
    """对已录制的演示重新执行步骤压缩"""
    from agent.human_demo_recorder import get_human_demo_recorder
    from agent.demo_step_compressor import compress_demo_steps

    rec = get_human_demo_recorder()
    session = rec.load(demo_id)
    if not session:
        return {"ok": False, "error": "演示不存在"}

    steps = compress_demo_steps(session)
    rec.save_session(session)

    return {
        "ok": True,
        "step_count": len(steps),
        "steps": [
            {"id": s.id, "action_type": s.action_type, "description": s.description}
            for s in steps
        ],
    }


@router.post("/{demo_id}/learn")
async def learn_from_demo(demo_id: str, body: LearnRequest):
    """触发 LLM 学习，分析演示并生成 Capsule"""
    from agent.human_demo_recorder import get_human_demo_recorder
    from agent.demo_learner import get_demo_learner
    from agent.demo_step_compressor import compress_demo_steps

    rec = get_human_demo_recorder()
    session = rec.load(demo_id)
    if not session:
        return {"ok": False, "error": "演示不存在"}

    # 确保已压缩
    if not session.steps:
        compress_demo_steps(session)

    learner = get_demo_learner()
    result = await learner.learn_and_register(session, auto_approve=body.auto_approve)

    # 保存更新后的会话
    rec.save_session(session)

    return {
        "ok": True,
        "inferred_goal": result.inferred_goal,
        "summary": result.summary,
        "confidence": result.confidence,
        "suggestions": result.suggestions,
        "capsule_id": result.capsule_id,
        "has_capsule": result.capsule_json is not None,
        "session_status": session.status,
    }


@router.post("/{demo_id}/approve")
async def approve_capsule(demo_id: str):
    """人工审批：将 LLM 生成的 Capsule 注册到系统"""
    from agent.human_demo_recorder import get_human_demo_recorder
    from agent.demo_learner import get_demo_learner

    rec = get_human_demo_recorder()
    session = rec.load(demo_id)
    if not session:
        return {"ok": False, "error": "演示不存在"}
    if not session.learning_result:
        return {"ok": False, "error": "尚未执行 LLM 学习，请先调用 /learn"}

    learner = get_demo_learner()
    capsule = learner.approve_capsule(session)
    if not capsule:
        return {"ok": False, "error": "Capsule 生成或注册失败"}

    rec.save_session(session)

    return {
        "ok": True,
        "capsule_id": capsule.id,
        "capsule": capsule.to_dict(),
    }


@router.get("/{demo_id}/capsule")
async def get_demo_capsule(demo_id: str):
    """查看演示生成的 Capsule 预览"""
    from agent.human_demo_recorder import get_human_demo_recorder

    rec = get_human_demo_recorder()
    session = rec.load(demo_id)
    if not session:
        return {"ok": False, "error": "演示不存在"}
    if not session.learning_result or not session.learning_result.capsule_json:
        return {"ok": False, "error": "尚未生成 Capsule"}

    return {
        "ok": True,
        "capsule": session.learning_result.capsule_json,
        "confidence": session.learning_result.confidence,
        "inferred_goal": session.learning_result.inferred_goal,
    }
