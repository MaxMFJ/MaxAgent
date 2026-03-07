"""
Duck REST API — 分身管理接口
提供 Duck 的增删查改、统计信息等 HTTP 端点。
"""
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from services.duck_protocol import DuckInfo, DuckStatus, DuckType
from services.duck_registry import DuckRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/duck", tags=["duck"])


@router.get("/list")
async def list_ducks(
    duck_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """列出所有 Duck"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    ducks = await registry.list_all()

    # 过滤
    if duck_type:
        ducks = [d for d in ducks if d.duck_type.value == duck_type]
    if status:
        ducks = [d for d in ducks if d.status.value == status]

    return {"ducks": [d.model_dump() for d in ducks]}


@router.get("/info/{duck_id}")
async def get_duck_info(duck_id: str):
    """获取单个 Duck 信息"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    duck = await registry.get(duck_id)
    if not duck:
        raise HTTPException(status_code=404, detail="Duck not found")
    return duck.model_dump()


@router.delete("/remove/{duck_id}")
async def remove_duck(duck_id: str):
    """删除一个 Duck"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    ok = await registry.unregister(duck_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Duck not found")
    return {"status": "ok", "duck_id": duck_id}


@router.get("/available")
async def list_available_ducks(duck_type: Optional[str] = None):
    """列出当前可用 (在线且空闲) 的 Duck"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    dt = DuckType(duck_type) if duck_type else None
    ducks = await registry.list_available(dt)
    return {"ducks": [d.model_dump() for d in ducks]}


@router.get("/stats")
async def duck_stats():
    """Duck 汇总统计"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    all_ducks = await registry.list_all()

    online = sum(1 for d in all_ducks if d.status == DuckStatus.ONLINE)
    busy = sum(1 for d in all_ducks if d.status == DuckStatus.BUSY)
    offline = sum(1 for d in all_ducks if d.status == DuckStatus.OFFLINE)
    total_completed = sum(d.completed_tasks for d in all_ducks)
    total_failed = sum(d.failed_tasks for d in all_ducks)

    by_type: dict[str, int] = {}
    for d in all_ducks:
        by_type[d.duck_type.value] = by_type.get(d.duck_type.value, 0) + 1

    return {
        "total": len(all_ducks),
        "online": online,
        "busy": busy,
        "offline": offline,
        "total_completed": total_completed,
        "total_failed": total_failed,
        "by_type": by_type,
    }


@router.post("/heartbeat-check")
async def trigger_heartbeat_check():
    """手动触发心跳超时巡检"""
    registry = DuckRegistry.get_instance()
    await registry.initialize()
    timed_out = await registry.check_heartbeats()
    return {"timed_out": timed_out}


# ─── 本地 Duck ───────────────────────────────────────


class CreateLocalDuckRequest(BaseModel):
    name: str = "Local Duck"
    duck_type: str = "general"
    skills: list[str] = Field(default_factory=list)


@router.post("/create-local")
async def create_local_duck(req: CreateLocalDuckRequest):
    """创建一个本地 Duck（同进程，内存通信）"""
    from services.local_duck_worker import get_local_duck_manager

    try:
        dt = DuckType(req.duck_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid duck_type: {req.duck_type}")

    manager = get_local_duck_manager()
    info = await manager.create_local_duck(
        name=req.name,
        duck_type=dt,
        skills=req.skills,
    )
    return {"status": "ok", "duck": info.model_dump()}


@router.delete("/local/{duck_id}")
async def destroy_local_duck(duck_id: str):
    """停止并删除一个本地 Duck"""
    from services.local_duck_worker import get_local_duck_manager

    manager = get_local_duck_manager()
    ok = await manager.destroy_local_duck(duck_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Local duck not found")
    return {"status": "ok", "duck_id": duck_id}


@router.get("/local/list")
async def list_local_ducks():
    """列出所有本地 Duck"""
    from services.local_duck_worker import get_local_duck_manager

    manager = get_local_duck_manager()
    duck_ids = manager.list_local_ducks()

    registry = DuckRegistry.get_instance()
    await registry.initialize()

    ducks = []
    for did in duck_ids:
        info = await registry.get(did)
        if info:
            ducks.append(info.model_dump())
    return {"count": len(ducks), "ducks": ducks}


# ─── Egg 生成系统 ────────────────────────────────────


class CreateEggRequest(BaseModel):
    duck_type: str = "general"
    name: Optional[str] = None
    main_agent_url: str = "ws://127.0.0.1:8765/duck/ws"


@router.post("/create-egg")
async def create_egg(req: CreateEggRequest):
    """创建新 Egg（指定鸭子类型）"""
    from app_state import IS_DUCK_MODE
    if IS_DUCK_MODE:
        raise HTTPException(status_code=403, detail="Duck 模式下禁止创建 Egg")

    from services.egg_builder import get_egg_builder

    try:
        dt = DuckType(req.duck_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid duck_type: {req.duck_type}")

    builder = get_egg_builder()
    record = builder.create_egg(
        duck_type=dt,
        name=req.name,
        main_agent_url=req.main_agent_url,
    )
    return {"status": "ok", "egg": record.to_dict()}


@router.get("/egg/{egg_id}/download")
async def download_egg(egg_id: str):
    """下载 Egg ZIP 文件"""
    from fastapi.responses import FileResponse
    from services.egg_builder import get_egg_builder

    builder = get_egg_builder()
    path = builder.get_egg_path(egg_id)
    if not path:
        raise HTTPException(status_code=404, detail="Egg not found")

    return FileResponse(
        path=str(path),
        media_type="application/zip",
        filename=f"{egg_id}.zip",
    )


@router.get("/eggs")
async def list_eggs():
    """列出所有已生成的 Egg"""
    from services.egg_builder import get_egg_builder

    builder = get_egg_builder()
    eggs = builder.list_eggs()
    return {"count": len(eggs), "eggs": [e.to_dict() for e in eggs]}


@router.delete("/egg/{egg_id}")
async def delete_egg(egg_id: str):
    """删除一个 Egg"""
    from services.egg_builder import get_egg_builder

    builder = get_egg_builder()
    ok = builder.delete_egg(egg_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Egg not found")
    return {"status": "ok", "egg_id": egg_id}


# ─── 模板查询 ────────────────────────────────────────


@router.get("/templates")
async def list_duck_templates():
    """列出所有可用 Duck 模板"""
    from services.duck_template import list_templates

    templates = list_templates()
    return {
        "count": len(templates),
        "templates": [
            {
                "duck_type": t.duck_type.value,
                "name": t.name,
                "description": t.description,
                "skills": t.skills,
                "icon": t.icon,
            }
            for t in templates
        ],
    }


# ─── 子 Duck 结果文件上传 ─────────────────────────────

_DUCK_RESULTS_DIR = Path(__file__).parent.parent / "data" / "duck_results"


@router.post("/upload-result")
async def upload_duck_result(
    duck_id: str = Form(...),
    task_id: str = Form(...),
    file: UploadFile = File(...),
    token: str = Form(default=""),
):
    """
    子 Duck 上传任务产出文件到主 Backend，供主 Agent 中转给用户。
    返回主 Backend 可访问的 URL。
    """
    from auth import verify_token
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    _DUCK_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 安全文件名：仅允许 duck_id/task_id 前缀 + 原始文件名
    safe_name = Path(file.filename or "result").name
    # 防止路径穿越
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        safe_name = f"result_{uuid.uuid4().hex[:8]}"

    save_dir = _DUCK_RESULTS_DIR / duck_id / task_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / safe_name

    try:
        content = await file.read()
        save_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # 返回相对 URL（可经 /duck/result-file 路由访问）
    rel_url = f"/duck/result-file/{duck_id}/{task_id}/{safe_name}"
    logger.info(
        "Duck result file saved: duck=%s task=%s file=%s size=%d",
        duck_id, task_id, safe_name, len(content),
    )
    return {
        "status": "ok",
        "duck_id": duck_id,
        "task_id": task_id,
        "filename": safe_name,
        "url": rel_url,
        "size": len(content),
    }


@router.get("/result-file/{duck_id}/{task_id}/{filename}")
async def get_duck_result_file(duck_id: str, task_id: str, filename: str):
    """下载子 Duck 上传的结果文件"""
    from fastapi.responses import FileResponse

    # 安全校验：防止路径穿越
    for part in (duck_id, task_id, filename):
        if ".." in part or "/" in part or "\\" in part:
            raise HTTPException(status_code=400, detail="Invalid path")

    path = _DUCK_RESULTS_DIR / duck_id / task_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    return FileResponse(path=str(path), filename=filename)


# ─── Duck 间消息中转 ─────────────────────────────────


class RelayMessageRequest(BaseModel):
    from_duck_id: str
    to_duck_id: str
    content: Any = None
    msg_type: str = "relay"


@router.post("/relay")
async def relay_message(req: RelayMessageRequest):
    """Duck → Duck 消息中转（经主 Agent）"""
    from services.duck_message_relay import get_message_relay

    relay = get_message_relay()
    ok = await relay.relay_message(
        from_duck_id=req.from_duck_id,
        to_duck_id=req.to_duck_id,
        content=req.content,
        msg_type=req.msg_type,
    )
    return {"status": "ok" if ok else "failed", "delivered": ok}


@router.get("/relay/log")
async def get_relay_log(duck_id: Optional[str] = None, limit: int = 50):
    """查询 Duck 间消息日志"""
    from services.duck_message_relay import get_message_relay

    relay = get_message_relay()
    logs = relay.get_message_log(duck_id=duck_id, limit=limit)
    return {"count": len(logs), "messages": logs}


# ─── DAG 任务编排 ────────────────────────────────────


class DAGNodeRequest(BaseModel):
    node_id: str
    description: str
    task_type: str = "general"
    params: dict = Field(default_factory=dict)
    duck_type: Optional[str] = None
    duck_id: Optional[str] = None
    timeout: int = 600
    priority: int = 0
    depends_on: list[str] = Field(default_factory=list)
    input_mapping: dict = Field(default_factory=dict)


class CreateDAGRequest(BaseModel):
    description: str
    nodes: list[DAGNodeRequest]


@router.post("/dag/create")
async def create_dag(req: CreateDAGRequest):
    """创建 DAG 任务流"""
    from services.duck_task_dag import DAGNode, get_dag_orchestrator

    orchestrator = get_dag_orchestrator()

    nodes = []
    for n in req.nodes:
        dt = DuckType(n.duck_type) if n.duck_type else None
        nodes.append(DAGNode(
            node_id=n.node_id,
            description=n.description,
            task_type=n.task_type,
            params=n.params,
            duck_type=dt,
            duck_id=n.duck_id,
            timeout=n.timeout,
            priority=n.priority,
            depends_on=n.depends_on,
            input_mapping=n.input_mapping,
        ))

    try:
        execution = orchestrator.create_dag(
            description=req.description,
            nodes=nodes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "dag": execution.to_dict()}


@router.post("/dag/{dag_id}/execute")
async def execute_dag(dag_id: str):
    """执行 DAG 任务流"""
    from services.duck_task_dag import get_dag_orchestrator

    orchestrator = get_dag_orchestrator()
    execution = orchestrator.get_execution(dag_id)
    if not execution:
        raise HTTPException(status_code=404, detail="DAG not found")

    await orchestrator.execute(dag_id)
    return {"status": "ok", "dag": execution.to_dict()}


@router.post("/dag/{dag_id}/cancel")
async def cancel_dag(dag_id: str):
    """取消 DAG 执行"""
    from services.duck_task_dag import get_dag_orchestrator

    orchestrator = get_dag_orchestrator()
    ok = await orchestrator.cancel(dag_id)
    if not ok:
        raise HTTPException(status_code=404, detail="DAG not found or already completed")
    return {"status": "ok", "dag_id": dag_id}


@router.get("/dag/{dag_id}")
async def get_dag_status(dag_id: str):
    """查询 DAG 执行状态"""
    from services.duck_task_dag import get_dag_orchestrator

    orchestrator = get_dag_orchestrator()
    execution = orchestrator.get_execution(dag_id)
    if not execution:
        raise HTTPException(status_code=404, detail="DAG not found")
    return execution.to_dict()


@router.get("/dag/list")
async def list_dags(status: Optional[str] = None):
    """列出所有 DAG 执行"""
    from services.duck_task_dag import get_dag_orchestrator

    orchestrator = get_dag_orchestrator()
    execs = orchestrator.list_executions(status=status)
    return {"count": len(execs), "dags": [e.to_dict() for e in execs]}
