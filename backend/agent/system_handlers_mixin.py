"""
SystemHandlersMixin — Action handlers for system/app/shell/clipboard operations.
Extracted from autonomous_agent.py.
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SystemHandlersMixin:
    """Mixin providing system, shell, app and clipboard action handlers for AutonomousAgent."""

    async def _handle_run_shell(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle run_shell action"""
        command = params.get("command", "")
        working_dir = params.get("working_directory", os.path.expanduser("~"))
        timeout = params.get("timeout", 60)

        if not command:
            return {"success": False, "error": "Command is empty"}

        if self._is_dangerous_command(command):
            return {"success": False, "error": f"Dangerous command blocked: {command}"}

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            return {
                "success": process.returncode == 0,
                "output": stdout_str or stderr_str,
                "error": stderr_str if process.returncode != 0 else None,
                "exit_code": process.returncode,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_create_script(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_and_run_script action"""
        language = params.get("language", "python")
        code = params.get("code", "")
        should_run = params.get("run", True)
        working_dir = params.get("working_directory", os.path.expanduser("~/Desktop"))

        if not code:
            return {"success": False, "error": "Code is empty"}

        ext_map = {"python": ".py", "bash": ".sh", "javascript": ".js", "shell": ".sh"}
        ext = ext_map.get(language.lower(), ".txt")

        runner_map = {"python": "python3", "bash": "bash", "javascript": "node", "shell": "bash"}
        runner = runner_map.get(language.lower())

        script_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=ext, delete=False, dir=working_dir
            ) as f:
                f.write(code)
                script_path = f.name

            if not should_run:
                return {"success": True, "output": f"Script saved to: {script_path}"}

            if not runner:
                return {"success": False, "error": f"Unsupported language: {language}"}

            process = await asyncio.create_subprocess_exec(
                runner, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            return {
                "success": process.returncode == 0,
                "output": stdout_str or stderr_str,
                "error": stderr_str if process.returncode != 0 else None,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Script execution timed out (120s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if script_path and should_run:
                try:
                    if os.path.exists(script_path):
                        os.unlink(script_path)
                except Exception:
                    pass

    async def _handle_open_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle open_app action（通过 runtime adapter）"""
        app_name = params.get("app_name", "")
        if not app_name:
            return {"success": False, "error": "App name is empty"}
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持应用控制"}
        ok, err = await self.runtime_adapter.open_app(app_name=app_name)
        return {
            "success": ok,
            "output": f"Opened: {app_name}" if ok else None,
            "error": err if not ok else None,
        }

    async def _handle_close_app(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle close_app action（通过 runtime adapter）"""
        app_name = params.get("app_name", "")
        if not app_name:
            return {"success": False, "error": "App name is empty"}
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持应用控制"}
        ok, err = await self.runtime_adapter.close_app(app_name)
        return {
            "success": ok,
            "output": f"Closed: {app_name}" if ok else None,
            "error": err if not ok else None,
        }

    async def _handle_system_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_system_info action"""
        import psutil

        info_type = params.get("info_type", "all")
        try:
            info = {}
            if info_type in ("cpu", "all"):
                info["cpu"] = {"percent": psutil.cpu_percent(interval=0.5), "count": psutil.cpu_count()}
            if info_type in ("memory", "all"):
                mem = psutil.virtual_memory()
                info["memory"] = {
                    "total_gb": round(mem.total / (1024 ** 3), 2),
                    "used_gb": round(mem.used / (1024 ** 3), 2),
                    "percent": mem.percent,
                }
            if info_type in ("disk", "all"):
                disk = psutil.disk_usage("/")
                info["disk"] = {
                    "total_gb": round(disk.total / (1024 ** 3), 2),
                    "used_gb": round(disk.used / (1024 ** 3), 2),
                    "percent": round(disk.percent, 1),
                }
            return {"success": True, "output": json.dumps(info, indent=2)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _handle_clipboard_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle clipboard_read action（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持剪贴板"}
        ok, content, err = await self.runtime_adapter.clipboard_read()
        return {"success": ok, "output": content if ok else None, "error": err if not ok else None}

    async def _handle_clipboard_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle clipboard_write action（通过 runtime adapter）"""
        content = params.get("content", "")
        if not self.runtime_adapter:
            return {"success": False, "error": "当前平台不支持剪贴板"}
        ok, err = await self.runtime_adapter.clipboard_write(content)
        return {
            "success": ok,
            "output": "Content copied to clipboard" if ok else None,
            "error": err if not ok else None,
        }

    async def _handle_think(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle think action - no actual execution"""
        thought = params.get("thought", "")
        return {"success": True, "output": f"Thought: {thought}"}

    async def _handle_finish(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle finish action"""
        summary = params.get("summary", "Task completed")
        success = params.get("success", True)
        return {"success": success, "output": summary}

    def _is_dangerous_command(self, command: str) -> bool:
        """Check if command is dangerous (delegate to safety module)."""
        from .action_schema import AgentAction, ActionType
        from .safety import validate_action_safe
        ok, _ = validate_action_safe(
            AgentAction(action_type=ActionType.RUN_SHELL, params={"command": command or ""}, reasoning="")
        )
        return not ok
