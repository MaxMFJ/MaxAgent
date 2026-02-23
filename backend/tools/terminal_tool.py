"""
Terminal Command Execution Tool
Execute shell commands with timeout and output capture
"""

import asyncio
import os
import shlex
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, ToolCategory


class TerminalTool(BaseTool):
    """Tool for executing terminal/shell commands"""
    
    name = "terminal"
    description = """终端命令执行工具，可以运行 shell 命令并返回输出。
支持功能：
- 执行任意 shell 命令
- 设置超时限制
- 指定工作目录
- 捕获标准输出和错误输出

安全提示：危险命令（如 rm -rf /）会被拒绝执行。"""
    
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令"
            },
            "working_directory": {
                "type": "string",
                "description": "命令执行的工作目录（可选，默认为用户主目录）"
            },
            "timeout": {
                "type": "integer",
                "description": "命令超时时间（秒），默认 30 秒",
                "default": 30
            },
            "shell": {
                "type": "boolean",
                "description": "是否通过 shell 执行（默认 True）",
                "default": True
            }
        },
        "required": ["command"]
    }
    
    category = ToolCategory.TERMINAL
    requires_confirmation = True
    
    DANGEROUS_PATTERNS = [
        "rm -rf /",
        "rm -rf /*",
        "rm -rf ~",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
        "chmod -R 777 /",
        "chown -R",
        "> /dev/sda",
        "mv /* ",
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "").strip()
        working_dir = kwargs.get("working_directory", os.path.expanduser("~"))
        timeout = kwargs.get("timeout", 30)
        use_shell = kwargs.get("shell", True)
        
        if not command:
            return ToolResult(success=False, error="命令不能为空")
        
        if self._is_dangerous(command):
            return ToolResult(success=False, error=f"安全限制：拒绝执行危险命令: {command}")
        
        working_dir = os.path.expanduser(working_dir)
        if not os.path.exists(working_dir):
            return ToolResult(success=False, error=f"工作目录不存在: {working_dir}")
        
        try:
            if use_shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir
                )
            else:
                args = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir
                )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    success=False,
                    error=f"命令执行超时（{timeout}秒）",
                    data={"command": command, "timeout": timeout}
                )
            
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            return ToolResult(
                success=process.returncode == 0,
                data={
                    "command": command,
                    "exit_code": process.returncode,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "working_directory": working_dir
                },
                error=stderr_str if process.returncode != 0 else None
            )
            
        except FileNotFoundError:
            return ToolResult(success=False, error=f"命令不存在: {command.split()[0]}")
        except PermissionError:
            return ToolResult(success=False, error="权限不足，无法执行命令")
        except Exception as e:
            return ToolResult(success=False, error=f"执行错误: {str(e)}")
    
    def _is_dangerous(self, command: str) -> bool:
        """Check if command matches dangerous patterns"""
        command_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in command_lower:
                return True
        return False
