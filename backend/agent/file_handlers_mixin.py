"""
FileHandlersMixin — Action handlers for file system operations.
Extracted from autonomous_agent.py.
"""

import logging
import os
import shutil
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FileHandlersMixin:
    """Mixin providing file system action handlers for AutonomousAgent."""

    async def _handle_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle read_file action, supports offset/limit for chunked reading"""
        path = os.path.expanduser(params.get("path", ""))
        encoding = params.get("encoding", "utf-8")

        # 文件读取缓存：防止反复读取同一文件导致上下文膨胀（全局生效）
        if not hasattr(self, '_read_file_cache'):
            self._read_file_cache = {}
        _cache_key = f"{path}:{params.get('offset', 0)}:{params.get('limit', 0)}"
        if path and _cache_key in self._read_file_cache:
            logger.info(f"[ReadCache] read_file cache hit: {path}")
            return self._read_file_cache[_cache_key]

        # 判断 Duck 模式（用于后续限制）
        _is_duck = getattr(self, 'isolated_context', False)
        if not _is_duck:
            try:
                from app_state import get_duck_context as _gdc_cache
                _is_duck = bool(_gdc_cache())
            except Exception:
                pass

        offset = int(params.get("offset", 0) or 0)
        limit = int(params.get("limit", 0) or 15000)
        if limit <= 0:
            limit = 15000

        # 全局读取限制：防止大内容导致 LLM 上下文膨胀超时
        if _is_duck and limit > 5000:
            limit = 5000
        elif limit > 8000:
            limit = 8000

        if not path:
            return {"success": False, "error": "Path is empty"}

        if not os.path.exists(path):
            return {"success": False, "error": f"File not found: {path}"}

        # 检测二进制文件（PNG/JPG/PDF 等），避免 UnicodeDecodeError
        BINARY_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
                             '.pdf', '.zip', '.tar', '.gz', '.exe', '.bin',
                             '.mp3', '.mp4', '.mov', '.avi', '.ico', '.tiff'}
        ext = os.path.splitext(path)[1].lower()
        if ext in BINARY_EXTENSIONS:
            size = os.path.getsize(path)
            return {
                "success": False,
                "error": f"该文件是二进制文件（{ext}），无法用 read_file 读取文本内容。"
                         f"文件大小：{size} 字节。请使用 run_shell + python 或 screenshot 等工具处理此类文件。"
            }

        try:
            file_size = os.path.getsize(path)
            BIG_FILE_THRESHOLD = 20 * 1024  # 20KB
            is_duck = getattr(self, 'isolated_context', False)
            if not is_duck:
                try:
                    from app_state import IS_DUCK_MODE
                    is_duck = IS_DUCK_MODE
                except ImportError:
                    pass

            # Duck + 大文件 + 从头读取（offset==0）：返回智能摘要
            if is_duck and file_size > BIG_FILE_THRESHOLD and offset == 0:
                with open(path, "r", encoding=encoding, errors="replace") as f:
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
                    f"\n如只需读取某段代码，用 read_file offset=N limit=M 精确读取。"
                )
                _big_result = {
                    "success": True,
                    "output": output,
                    "content": output,
                    "total_size": sum(len(l) for l in lines),
                    "truncated": True,
                    "smart_summary": True,
                }
                if path and hasattr(self, '_read_file_cache'):
                    self._read_file_cache[_cache_key] = _big_result
                return _big_result

            with open(path, "r", encoding=encoding, errors="replace") as f:
                full_content = f.read()
            total = len(full_content)

            if offset > 0 or limit < total:
                content = full_content[offset: offset + limit]
                truncated = offset + limit < total
                hint = (
                    f"共 {total} 字符，已读 {offset}–{offset + len(content)}。"
                    f"若需后续内容可 read_file offset={offset + len(content)} limit={limit}"
                    if truncated else None
                )
                _chunk_result = {
                    "success": True,
                    "output": content + (f"\n\n[分段提示] {hint}" if hint else ""),
                    "content": content,
                    "total_size": total,
                    "truncated": truncated,
                }
                if path and hasattr(self, '_read_file_cache'):
                    self._read_file_cache[_cache_key] = _chunk_result
                return _chunk_result

            _full_result = {"success": True, "output": full_content, "content": full_content}
            if path and hasattr(self, '_read_file_cache'):
                self._read_file_cache[_cache_key] = _full_result
            return _full_result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_write_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle write_file action"""
        path = os.path.expanduser(params.get("path", ""))
        content = params.get("content", "")
        append = params.get("append", False)
        encoding = params.get("encoding", "utf-8")

        if not path:
            return {"success": False, "error": "Path is empty"}

        # v3.4 snapshot before write
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "write", path,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
            )
        except Exception:
            pass

        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode, encoding=encoding) as f:
                f.write(content)
            return {"success": True, "output": f"Written to: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_move_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle move_file action"""
        source = os.path.expanduser(params.get("source", ""))
        destination = os.path.expanduser(params.get("destination", ""))

        if not source or not destination:
            return {"success": False, "error": "Source or destination is empty"}

        if not os.path.exists(source):
            return {"success": False, "error": f"Source not found: {source}"}

        # v3.4 snapshot before move
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "move", source,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
                destination=destination,
            )
        except Exception:
            pass

        try:
            shutil.move(source, destination)
            return {"success": True, "output": f"Moved: {source} -> {destination}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_copy_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle copy_file action"""
        source = os.path.expanduser(params.get("source", ""))
        destination = os.path.expanduser(params.get("destination", ""))

        if not source or not destination:
            return {"success": False, "error": "Source or destination is empty"}

        if not os.path.exists(source):
            return {"success": False, "error": f"Source not found: {source}"}

        # v3.4 snapshot before copy
        try:
            from .snapshot_manager import get_snapshot_manager
            get_snapshot_manager().capture(
                "copy", source,
                task_id=getattr(self, "_current_task_id", ""),
                session_id=getattr(self, "_current_session_id", ""),
                destination=destination,
            )
        except Exception:
            pass

        try:
            if os.path.isdir(source):
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            return {"success": True, "output": f"Copied: {source} -> {destination}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_delete_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle delete_file action"""
        path = os.path.expanduser(params.get("path", ""))
        recursive = params.get("recursive", False)

        if not path:
            return {"success": False, "error": "Path is empty"}

        if not os.path.exists(path):
            return {"success": False, "error": f"Path not found: {path}"}

        # 使用 realpath 规范化路径，防止通过符号链接或 .. 绕过检查
        real_path = os.path.realpath(path)
        home_dir = os.path.realpath(os.path.expanduser("~"))

        # 危险路径列表（包括绝对根目录和系统路径）
        dangerous_exact = ["/", "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var", home_dir]
        dangerous_prefixes = ["/System/", "/Library/", "/usr/", "/bin/", "/sbin/", "/etc/", "/var/", "/private/"]

        if real_path in dangerous_exact:
            return {"success": False, "error": f"Cannot delete protected path: {real_path}"}

        for prefix in dangerous_prefixes:
            if real_path.startswith(prefix):
                return {"success": False, "error": f"Cannot delete system path: {real_path}"}

        try:
            if os.path.isdir(real_path):
                if recursive:
                    shutil.rmtree(real_path)
                else:
                    os.rmdir(real_path)
            else:
                os.unlink(real_path)
            return {"success": True, "output": f"Deleted: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_list_directory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle list_directory action"""
        path = os.path.expanduser(params.get("path", ""))
        recursive = params.get("recursive", False)
        pattern = params.get("pattern")

        if not path:
            return {"success": False, "error": "Path is empty"}

        if not os.path.exists(path):
            return {"success": False, "error": f"Path not found: {path}"}

        try:
            if recursive:
                items = []
                for root, dirs, files in os.walk(path):
                    for name in files + dirs:
                        full_path = os.path.join(root, name)
                        rel_path = os.path.relpath(full_path, path)
                        if pattern and pattern not in name:
                            continue
                        items.append(rel_path)
                        if len(items) > 500:
                            break
                    if len(items) > 500:
                        break
            else:
                items = os.listdir(path)
                if pattern:
                    items = [i for i in items if pattern in i]

            return {"success": True, "output": "\n".join(items[:100])}
        except Exception as e:
            return {"success": False, "error": str(e)}
