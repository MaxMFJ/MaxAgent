"""
RPA (Robotic Process Automation) 路由

提供 Runbook 的增删查导入 API，供 Mac App 设置页面调用。
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

router = APIRouter()


# ─── 请求/响应体 ──────────────────────────────────────────────────────────────

class RunbookImportRequest(BaseModel):
    """直接以 JSON body 导入 Runbook（适合 API 调用）"""
    data: Dict[str, Any]
    overwrite: bool = False


# ─── 列表 / 查询 ──────────────────────────────────────────────────────────────

@router.get("/runbooks")
async def runbooks_list(category: Optional[str] = None, tag: Optional[str] = None):
    """列出所有（或按类别/标签过滤）Runbook"""
    try:
        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        if category:
            items = reg.find_by_category(category)
        elif tag:
            items = reg.find_by_tag(tag)
        else:
            items = reg.list_all()
        return {
            "count": len(items),
            "runbooks": [rb.to_dict(include_steps=False) for rb in items],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runbooks/search")
async def runbooks_search(q: str, limit: int = 5):
    """按自然语言查询搜索 Runbook"""
    try:
        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        items = reg.find_by_query(q, limit=limit)
        return {
            "query": q,
            "count": len(items),
            "runbooks": [rb.to_dict(include_steps=False) for rb in items],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runbooks/{runbook_id}")
async def runbooks_get(runbook_id: str):
    """获取单个 Runbook 详情（含完整步骤）"""
    try:
        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        rb = reg.get(runbook_id)
        if not rb:
            raise HTTPException(status_code=404, detail=f"Runbook '{runbook_id}' not found")
        return rb.to_dict(include_steps=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 导入 ─────────────────────────────────────────────────────────────────────

@router.post("/runbooks/import")
async def runbooks_import(request: RunbookImportRequest):
    """通过 JSON body 导入 Runbook"""
    try:
        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        rb = reg.import_runbook(request.data, overwrite=request.overwrite)
        return {"success": True, "runbook_id": rb.id, "name": rb.name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runbooks/upload")
async def runbooks_upload(file: UploadFile = File(...), overwrite: bool = False):
    """通过文件上传（YAML 或 JSON）导入 Runbook"""
    import json
    try:
        content = await file.read()
        filename = file.filename or ""

        if filename.endswith((".yaml", ".yml")):
            try:
                import yaml
                data = yaml.safe_load(content.decode("utf-8"))
            except ImportError:
                raise HTTPException(status_code=400, detail="PyYAML not installed; use JSON format")
        else:
            data = json.loads(content.decode("utf-8"))

        if not isinstance(data, dict) or "id" not in data:
            raise HTTPException(status_code=400, detail="File must be a JSON/YAML object with an 'id' field")

        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        rb = reg.import_runbook(data, overwrite=overwrite)
        return {"success": True, "runbook_id": rb.id, "name": rb.name}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 删除 ─────────────────────────────────────────────────────────────────────

@router.delete("/runbooks/{runbook_id}")
async def runbooks_delete(runbook_id: str):
    """删除指定 Runbook"""
    try:
        from agent.runbook_registry import get_runbook_registry
        reg = get_runbook_registry()
        ok = reg.delete_runbook(runbook_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Runbook '{runbook_id}' not found")
        return {"success": True, "deleted": runbook_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
