"""文件下载路由：为远程客户端（iOS/Web）提供文件下载与预览能力"""
import os
import mimetypes
import logging
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/files", tags=["files"])

# 安全限制：禁止访问的路径前缀
BLOCKED_PREFIXES = [
    "/System",
    "/usr",
    "/bin",
    "/sbin",
    "/etc/shadow",
    "/etc/passwd",
    "/private/etc",
]

# 允许预览的文本类 MIME 类型
TEXT_PREVIEW_MIMES = {
    "text/plain", "text/html", "text/css", "text/javascript",
    "text/markdown", "text/csv", "text/xml", "text/yaml",
    "application/json", "application/xml", "application/javascript",
    "application/x-yaml", "application/x-python", "application/x-sh",
}

# 常见文件扩展名到图标的映射
FILE_ICONS = {
    # 文档
    ".pdf": "doc.fill",
    ".doc": "doc.fill",
    ".docx": "doc.fill",
    ".txt": "doc.text",
    ".md": "doc.text",
    ".rtf": "doc.text",
    # 表格
    ".xls": "tablecells",
    ".xlsx": "tablecells",
    ".csv": "tablecells",
    # 演示
    ".ppt": "play.rectangle",
    ".pptx": "play.rectangle",
    ".key": "play.rectangle",
    # 图片
    ".png": "photo",
    ".jpg": "photo",
    ".jpeg": "photo",
    ".gif": "photo",
    ".webp": "photo",
    ".svg": "photo",
    ".bmp": "photo",
    ".ico": "photo",
    # 压缩
    ".zip": "doc.zipper",
    ".tar": "doc.zipper",
    ".gz": "doc.zipper",
    ".rar": "doc.zipper",
    ".7z": "doc.zipper",
    # 代码
    ".py": "chevron.left.forwardslash.chevron.right",
    ".js": "chevron.left.forwardslash.chevron.right",
    ".ts": "chevron.left.forwardslash.chevron.right",
    ".swift": "chevron.left.forwardslash.chevron.right",
    ".java": "chevron.left.forwardslash.chevron.right",
    ".c": "chevron.left.forwardslash.chevron.right",
    ".cpp": "chevron.left.forwardslash.chevron.right",
    ".h": "chevron.left.forwardslash.chevron.right",
    ".html": "chevron.left.forwardslash.chevron.right",
    ".css": "chevron.left.forwardslash.chevron.right",
    ".json": "chevron.left.forwardslash.chevron.right",
    ".xml": "chevron.left.forwardslash.chevron.right",
    ".yaml": "chevron.left.forwardslash.chevron.right",
    ".yml": "chevron.left.forwardslash.chevron.right",
    ".sh": "terminal",
    # 音视频
    ".mp3": "music.note",
    ".mp4": "film",
    ".mov": "film",
    ".avi": "film",
    ".wav": "waveform",
    # 其他
    ".dmg": "externaldrive",
    ".app": "app",
    ".log": "doc.text",
}


def _validate_path(path: str) -> str:
    """验证并规范化文件路径，防止目录穿越攻击"""
    original = path
    # 规范化路径（消除 ../ ./ 等，解析符号链接）
    path = os.path.realpath(path)
    
    # 检查被禁路径
    for prefix in BLOCKED_PREFIXES:
        if path.startswith(prefix):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied: system path not allowed"
            )
    
    # 检查文件是否存在
    if not os.path.exists(path):
        logger.warning(f"File not found. original='{original}', resolved='{path}'")
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    
    return path


def _get_file_icon(ext: str) -> str:
    """根据扩展名返回 SF Symbol 图标名"""
    return FILE_ICONS.get(ext.lower(), "doc")


def _format_file_size(size: int) -> str:
    """格式化文件大小"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


@router.get("/info")
async def file_info(path: str = Query(..., description="文件绝对路径")):
    """
    获取文件元信息（大小、类型、图标等）。
    用于前端在下载前展示文件信息。
    """
    logger.info(f"[info] raw path param: '{path}' (repr: {repr(path)})")
    validated = _validate_path(path)
    
    is_dir = os.path.isdir(validated)
    stat = os.stat(validated)
    _, ext = os.path.splitext(validated)
    mime_type, _ = mimetypes.guess_type(validated)
    
    info = {
        "path": validated,
        "name": os.path.basename(validated),
        "is_directory": is_dir,
        "size": stat.st_size if not is_dir else 0,
        "size_formatted": _format_file_size(stat.st_size) if not is_dir else "-",
        "extension": ext,
        "mime_type": mime_type or "application/octet-stream",
        "icon": _get_file_icon(ext) if not is_dir else "folder",
        "modified": stat.st_mtime,
        "can_preview": (mime_type in TEXT_PREVIEW_MIMES) if mime_type else False,
    }
    
    # 如果是目录，列出内容
    if is_dir:
        try:
            entries = []
            for entry in os.scandir(validated):
                entry_ext = os.path.splitext(entry.name)[1]
                entry_mime, _ = mimetypes.guess_type(entry.name)
                entries.append({
                    "name": entry.name,
                    "is_directory": entry.is_dir(),
                    "size": entry.stat().st_size if not entry.is_dir() else 0,
                    "size_formatted": _format_file_size(entry.stat().st_size) if not entry.is_dir() else "-",
                    "extension": entry_ext,
                    "icon": _get_file_icon(entry_ext) if not entry.is_dir() else "folder",
                    "path": entry.path,
                })
            info["children"] = sorted(entries, key=lambda e: (not e["is_directory"], e["name"].lower()))
        except PermissionError:
            info["children"] = []
            info["error"] = "Permission denied"
    
    return info


@router.get("/download")
async def download_file(path: str = Query(..., description="文件绝对路径")):
    """
    下载文件。返回文件内容，支持浏览器直接下载。
    """
    logger.info(f"[download] raw path param: '{path}' (repr: {repr(path)})")
    validated = _validate_path(path)
    
    if os.path.isdir(validated):
        raise HTTPException(status_code=400, detail="Cannot download a directory")
    
    filename = os.path.basename(validated)
    mime_type, _ = mimetypes.guess_type(validated)
    
    logger.info(f"File download: {validated} ({_format_file_size(os.path.getsize(validated))})")
    
    return FileResponse(
        path=validated,
        filename=filename,
        media_type=mime_type or "application/octet-stream",
    )


@router.get("/preview")
async def preview_file(
    path: str = Query(..., description="文件绝对路径"),
    max_lines: int = Query(200, description="最大行数"),
):
    """
    预览文本文件内容。仅支持文本类型文件。
    """
    validated = _validate_path(path)
    
    if os.path.isdir(validated):
        raise HTTPException(status_code=400, detail="Cannot preview a directory")
    
    mime_type, _ = mimetypes.guess_type(validated)
    if mime_type and mime_type not in TEXT_PREVIEW_MIMES:
        # 对于未知类型，尝试读取一小段判断是否是文本
        if mime_type and not mime_type.startswith("text/"):
            try:
                with open(validated, "rb") as f:
                    sample = f.read(512)
                    # 简单检查是否包含大量非文本字节
                    non_text = sum(1 for b in sample if b < 8 or (b > 13 and b < 32))
                    if non_text > len(sample) * 0.3:
                        raise HTTPException(
                            status_code=400,
                            detail=f"File is not a text file (mime: {mime_type})"
                        )
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Cannot determine file type")
    
    try:
        # 尝试多种编码
        content = None
        for encoding in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(validated, "r", encoding=encoding) as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append(f"\n... (truncated at {max_lines} lines)")
                            break
                        lines.append(line)
                    content = "".join(lines)
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise HTTPException(status_code=400, detail="Cannot decode file content")
        
        _, ext = os.path.splitext(validated)
        return {
            "path": validated,
            "name": os.path.basename(validated),
            "content": content,
            "mime_type": mime_type or "text/plain",
            "extension": ext,
            "total_lines": content.count("\n") + 1,
            "truncated": len(content.splitlines()) >= max_lines,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
