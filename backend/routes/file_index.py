"""文件索引 API — workspace 文件扫描、索引构建、语义搜索"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from agent.file_index import get_file_index

router = APIRouter(prefix="/file-index", tags=["file-index"])


class ScanRequest(BaseModel):
    root: str  # workspace 根目录
    force: bool = False  # 强制全量重建


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    min_score: float = 0.3


@router.post("/scan")
async def scan_workspace(body: ScanRequest):
    """
    扫描 workspace 并构建向量索引。
    首次扫描较慢（需嵌入），后续增量扫描较快。
    """
    idx = get_file_index()
    scan_result = idx.scan_workspace(root=body.root, force=body.force)
    build_ok = idx.build_index()
    return {
        "ok": build_ok,
        "scan": scan_result,
        "stats": idx.get_stats(),
    }


@router.post("/search")
async def search_files(body: SearchRequest):
    """自然语言搜索文件"""
    idx = get_file_index()
    results = idx.search(query=body.query, top_k=body.top_k, min_score=body.min_score)
    return {"results": results}


@router.get("/stats")
async def index_stats():
    """获取索引统计信息"""
    idx = get_file_index()
    return idx.get_stats()


@router.get("/files")
async def list_indexed_files():
    """列出所有已索引文件"""
    idx = get_file_index()
    return {"files": idx.list_files()}
