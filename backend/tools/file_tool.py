"""
File Operations Tool
Provides file system operations: read, write, create, delete, move, list
"""

import os
import shutil
import getpass
import glob as glob_module
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, ToolCategory


def _normalize_path(path: str) -> str:
    """展开 ~、$(whoami)、$HOME 等为实际路径"""
    path = os.path.expanduser(path)
    # $(whoami) 和 ${whoami} 在 shell 中会执行，Python 需显式替换
    username = getpass.getuser()
    path = path.replace("$(whoami)", username).replace("${whoami}", username)
    path = os.path.expandvars(path)
    return path


# 允许访问的路径根列表
_ALLOWED_ROOTS = [
    os.path.expanduser("~"),
    "/tmp",
    "/var/folders",  # macOS 临时目录
]


def _check_path_allowed(path: str) -> None:
    """检查路径是否在允许范围内，防止访问系统敏感文件"""
    normalized = os.path.normpath(os.path.realpath(path))
    if any(normalized.startswith(root) for root in _ALLOWED_ROOTS):
        return
    raise PermissionError(f"路径不在允许范围内: {path}")


class FileTool(BaseTool):
    """Tool for file system operations"""
    
    name = "file_operations"
    description = """文件系统操作工具，支持以下操作：
- read: 读取文件内容
- write: 写入内容到文件
- create: 创建文件或目录
- delete: 删除文件或目录
- move: 移动或重命名文件/目录
- copy: 复制文件或目录
- list: 列出目录内容
- search: 搜索文件（支持通配符）
- info: 获取文件/目录信息"""
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "create", "delete", "move", "copy", "list", "search", "info"],
                "description": "要执行的操作类型"
            },
            "path": {
                "type": "string",
                "description": "目标文件或目录的路径"
            },
            "content": {
                "type": "string",
                "description": "写入文件的内容（用于 write 操作；create 时若提供则写入该内容，否则创建空文件）"
            },
            "destination": {
                "type": "string",
                "description": "目标路径（用于 move/copy 操作）"
            },
            "is_directory": {
                "type": "boolean",
                "description": "是否创建目录（用于 create 操作）",
                "default": False
            },
            "pattern": {
                "type": "string",
                "description": "搜索模式（用于 search 操作，支持 * 和 ** 通配符）"
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归操作",
                "default": False
            },
            "offset": {
                "type": "integer",
                "description": "（仅 read）从第 N 字符开始读取，用于分段读取大文件，默认 0"
            },
            "limit": {
                "type": "integer",
                "description": "（仅 read）最多读取字符数，默认 15000。超长文件可配合 offset 分段读取"
            }
        },
        "required": ["action", "path"]
    }
    
    category = ToolCategory.FILE
    requires_confirmation = False  # Will be True for delete operations
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        path = kwargs.get("path")
        
        if not path:
            return ToolResult(success=False, error="缺少路径参数")

        path = _normalize_path(path)
        _check_path_allowed(path)
        
        try:
            if action == "read":
                offset = int(kwargs.get("offset", 0) or 0)
                limit = int(kwargs.get("limit", 0) or 15000)
                if limit <= 0:
                    limit = 15000
                # Duck 模式强制限制 read limit，防止上下文爆炸
                try:
                    from app_state import get_duck_context
                    if get_duck_context() is not None:
                        limit = min(limit, 4000)
                except ImportError:
                    pass
                return await self._read(path, offset=offset, limit=limit)
            elif action == "write":
                content = kwargs.get("content", "")
                return await self._write(path, content)
            elif action == "create":
                is_dir = kwargs.get("is_directory", False)
                content = kwargs.get("content", "")
                return await self._create(path, is_dir, content=content)
            elif action == "delete":
                recursive = kwargs.get("recursive", False)
                return await self._delete(path, recursive)
            elif action == "move":
                dest = kwargs.get("destination")
                if not dest:
                    return ToolResult(success=False, error="移动操作需要 destination 参数")
                dest = _normalize_path(dest)
                _check_path_allowed(dest)
                return await self._move(path, dest)
            elif action == "copy":
                dest = kwargs.get("destination")
                if not dest:
                    return ToolResult(success=False, error="复制操作需要 destination 参数")
                dest = _normalize_path(dest)
                _check_path_allowed(dest)
                return await self._copy(path, dest)
            elif action == "list":
                return await self._list(path)
            elif action == "search":
                pattern = kwargs.get("pattern", "*")
                return await self._search(path, pattern)
            elif action == "info":
                return await self._info(path)
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
        except PermissionError:
            return ToolResult(success=False, error=f"权限不足: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _read(self, path: str, offset: int = 0, limit: int = 15000) -> ToolResult:
        """Read file content, supports offset/limit for chunked reading of large files"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, error=f"路径是目录，不是文件: {path}")

        # Duck 模式下大文件主动拦截：返回摘要+首尾片段
        BIG_FILE_THRESHOLD = 10 * 1024  # 10KB（从 20KB 降低，更积极防止上下文爆炸）
        file_size = os.path.getsize(path)
        is_duck = False
        try:
            from app_state import get_duck_context
            is_duck = get_duck_context() is not None
        except ImportError:
            pass
        if is_duck and file_size > BIG_FILE_THRESHOLD:
            # 有 offset 时返回精确分段（已被上面 limit=4000 限制）
            if offset > 0:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    full_content = f.read()
                total_size = len(full_content)
                segment = full_content[offset : offset + limit]
                truncated = offset + limit < total_size
                hint = (
                    f"\n\n[分段提示] 共 {total_size} 字符，已读 {offset}–{offset + len(segment)}。"
                    f"\n⚠️ Duck模式下请避免反复分段读取整个大文件，改用 create_and_run_script 处理。"
                ) if truncated else ""
                return ToolResult(
                    success=True,
                    data={"path": path, "content": segment + hint, "size": len(segment), "total_size": total_size, "offset": offset, "truncated": truncated},
                )
            # offset=0: 摘要模式
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total_lines = len(lines)
            head_lines = 80
            tail_lines = 30
            head = "".join(lines[:head_lines])
            tail = "".join(lines[-tail_lines:]) if total_lines > head_lines + tail_lines else ""
            summary_block = ""
            try:
                from services.file_structure_service import get_file_structure_summary
                summary = get_file_structure_summary(path)
                if summary:
                    summary_block = f"\n\n【结构摘要】\n{summary}"
            except Exception:
                pass
            omitted = total_lines - head_lines - (tail_lines if tail else 0)
            mid_hint = f"\n\n... [省略中间 {omitted} 行] ...\n\n" if tail and omitted > 0 else ""
            output = (
                f"【大文件智能读取】文件共 {total_lines} 行（{file_size} 字节），已启用摘要模式。"
                f"{summary_block}"
                f"\n\n【前 {head_lines} 行】\n{head}"
                f"{mid_hint}"
                f"{'【后 ' + str(tail_lines) + ' 行】' + chr(10) + tail if tail else ''}"
                f"\n\n⚠️ 【禁止全量读取】你已获得文件结构摘要和首尾内容，禁止再次从 offset=0 读取全文。"
                f"\n✅ 【正确做法】使用 create_and_run_script 编写 Python 脚本来修改此文件。"
                f"脚本中 open('{path}') 读全文，用字符串替换/正则修改后写回。"
                f"\n如只需读取某段代码，用 read offset=N limit=M 精确读取（每次最多4000字符）。"
            )
            return ToolResult(
                success=True,
                data={"path": path, "content": output, "size": len(output), "total_size": sum(len(l) for l in lines), "truncated": True, "smart_summary": True},
            )

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            full_content = f.read()
        total_size = len(full_content)

        if offset > 0 or limit < total_size:
            content = full_content[offset : offset + limit]
            truncated = offset + limit < total_size
            hint = f"\n\n[分段提示] 共 {total_size} 字符，已读 {offset}–{offset + len(content)}。若需后续内容可 read offset={offset + len(content)} limit={limit}" if truncated else ""
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "content": content + hint,
                    "size": len(content),
                    "total_size": total_size,
                    "offset": offset,
                    "truncated": truncated,
                },
            )
        return ToolResult(success=True, data={"path": path, "content": full_content, "size": total_size})
    
    async def _write(self, path: str, content: str) -> ToolResult:
        """Write content to file"""
        # v3.4 snapshot before overwrite
        try:
            from agent.snapshot_manager import get_snapshot_manager
            _task_id = getattr(self, "_current_task_id", "")
            _session_id = getattr(self, "_current_session_id", "")
            get_snapshot_manager().capture("write", path, task_id=_task_id, session_id=_session_id)
        except Exception:
            pass
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return ToolResult(success=True, data={"path": path, "bytes_written": len(content.encode("utf-8"))})
    
    async def _create(self, path: str, is_directory: bool, content: str = "") -> ToolResult:
        """Create file or directory. If content is provided and path is a file, write content instead of empty file."""
        if os.path.exists(path):
            return ToolResult(
                success=False,
                error=f"路径已存在: {path}",
                data={
                    "file_exists": True,
                    "path": path,
                    "suggestion": "请先用 read 读取该路径内容，若已满足需求则直接告知用户使用方法，不要重复创建或创建「更简单」版本"
                }
            )
        
        if is_directory:
            os.makedirs(path, exist_ok=True)
            return ToolResult(success=True, data={"path": path, "type": "directory"})
        else:
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            if content:
                # 创建并写入内容（与 write 一致），避免“创建空文件”导致报告为空
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(success=True, data={"path": path, "type": "file", "bytes_written": len(content.encode("utf-8"))})
            Path(path).touch()
            return ToolResult(success=True, data={"path": path, "type": "file"})
    
    async def _delete(self, path: str, recursive: bool) -> ToolResult:
        """Delete file or directory"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"路径不存在: {path}")
        
        # v3.4 snapshot before delete
        try:
            from agent.snapshot_manager import get_snapshot_manager
            _task_id = getattr(self, "_current_task_id", "")
            _session_id = getattr(self, "_current_session_id", "")
            get_snapshot_manager().capture("delete", path, task_id=_task_id, session_id=_session_id)
        except Exception:
            pass
        if os.path.isdir(path):
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
        else:
            os.remove(path)
        
        return ToolResult(success=True, data={"deleted": path})
    
    async def _move(self, src: str, dest: str) -> ToolResult:
        """Move/rename file or directory"""
        if not os.path.exists(src):
            return ToolResult(success=False, error=f"源路径不存在: {src}")
        
        # v3.4 snapshot before move
        try:
            from agent.snapshot_manager import get_snapshot_manager
            _task_id = getattr(self, "_current_task_id", "")
            _session_id = getattr(self, "_current_session_id", "")
            get_snapshot_manager().capture("move", src, task_id=_task_id, session_id=_session_id, destination=dest)
        except Exception:
            pass
        shutil.move(src, dest)
        return ToolResult(success=True, data={"from": src, "to": dest})
    
    async def _copy(self, src: str, dest: str) -> ToolResult:
        """Copy file or directory"""
        if not os.path.exists(src):
            return ToolResult(success=False, error=f"源路径不存在: {src}")
        
        # v3.4 snapshot destination path (to support undo of copy)
        try:
            from agent.snapshot_manager import get_snapshot_manager
            _task_id = getattr(self, "_current_task_id", "")
            _session_id = getattr(self, "_current_session_id", "")
            get_snapshot_manager().capture("copy", src, task_id=_task_id, session_id=_session_id, destination=dest)
        except Exception:
            pass
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
        
        return ToolResult(success=True, data={"from": src, "to": dest})
    
    async def _list(self, path: str) -> ToolResult:
        """List directory contents"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"目录不存在: {path}")
        if not os.path.isdir(path):
            return ToolResult(success=False, error=f"路径不是目录: {path}")
        
        items = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            stat = os.stat(item_path)
            items.append({
                "name": item,
                "type": "directory" if os.path.isdir(item_path) else "file",
                "size": stat.st_size if os.path.isfile(item_path) else None,
                "modified": stat.st_mtime
            })
        
        return ToolResult(success=True, data={"path": path, "items": items, "count": len(items)})
    
    async def _search(self, path: str, pattern: str) -> ToolResult:
        """Search files with pattern"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"搜索路径不存在: {path}")
        
        search_pattern = os.path.join(path, "**", pattern) if "**" not in pattern else os.path.join(path, pattern)
        matches = glob_module.glob(search_pattern, recursive=True)
        
        results = [{"path": m, "type": "directory" if os.path.isdir(m) else "file"} for m in matches[:100]]
        
        return ToolResult(success=True, data={"pattern": pattern, "matches": results, "count": len(matches)})
    
    async def _info(self, path: str) -> ToolResult:
        """Get file/directory info"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"路径不存在: {path}")
        
        stat = os.stat(path)
        info = {
            "path": path,
            "absolute_path": os.path.abspath(path),
            "type": "directory" if os.path.isdir(path) else "file",
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "accessed": stat.st_atime,
            "permissions": oct(stat.st_mode)[-3:]
        }
        
        return ToolResult(success=True, data=info)
