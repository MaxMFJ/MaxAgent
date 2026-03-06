"""
File Operations Tool
Provides file system operations: read, write, create, delete, move, list
"""

import os
import shutil
import glob as glob_module
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, ToolCategory


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
        
        path = os.path.expanduser(path)
        
        try:
            if action == "read":
                return await self._read(path)
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
                return await self._move(path, os.path.expanduser(dest))
            elif action == "copy":
                dest = kwargs.get("destination")
                if not dest:
                    return ToolResult(success=False, error="复制操作需要 destination 参数")
                return await self._copy(path, os.path.expanduser(dest))
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
    
    async def _read(self, path: str) -> ToolResult:
        """Read file content"""
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, error=f"路径是目录，不是文件: {path}")
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        return ToolResult(success=True, data={"path": path, "content": content, "size": len(content)})
    
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
