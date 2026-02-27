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
- **background**：启动 Flask、Node 开发服务器等长期运行进程时必设为 true，否则会超时失败

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
                "description": "命令超时时间（秒），默认 120 秒（pip/npm 等安装命令建议使用 300 秒）",
                "default": 120
            },
            "shell": {
                "type": "boolean",
                "description": "是否通过 shell 执行（默认 True）",
                "default": True
            },
            "background": {
                "type": "boolean",
                "description": "是否后台运行（Flask、flask run、npm run dev、python app.py 等长期运行进程必须设为 true）",
                "default": False
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
        timeout = kwargs.get("timeout", 120)
        use_shell = kwargs.get("shell", True)
        background = kwargs.get("background", False)
        
        if not command:
            return ToolResult(success=False, error="命令不能为空")
        
        if self._is_dangerous(command):
            return ToolResult(success=False, error=f"安全限制：拒绝执行危险命令: {command}")
        
        working_dir = os.path.expanduser(working_dir)
        if not os.path.exists(working_dir):
            return ToolResult(success=False, error=f"工作目录不存在: {working_dir}")
        
        # 后台模式：Flask/开发服务器等长期运行进程，不等待退出
        if background:
            return await self._run_background(command, working_dir, use_shell)
        
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
                    error=f"命令执行超时（{timeout}秒）。若为 Flask/开发服务器等长期运行进程，请使用 background: true",
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
    
    async def _run_background(self, command: str, working_dir: str, use_shell: bool) -> ToolResult:
        """后台运行：启动进程后立即返回，不等待进程退出。适用于 Flask、npm run dev 等长期运行进程。"""
        log_base = f"/tmp/terminal_bg_{os.getpid()}"
        stdout_log = f"{log_base}_stdout.log"
        stderr_log = f"{log_base}_stderr.log"
        # nohup 确保进程脱离当前会话，& 后台运行；cwd 已由 create_subprocess_shell 设置
        bg_cmd = f"nohup ({command}) > {stdout_log} 2> {stderr_log} &"
        process = await asyncio.create_subprocess_shell(
            bg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return ToolResult(success=False, error="后台启动命令本身超时")
        # 启动命令（nohup ... &）通常立即返回
        return ToolResult(
            success=True,
            data={
                "command": command,
                "mode": "background",
                "message": f"进程已在后台启动。输出见 {stdout_log} 和 {stderr_log}",
                "stdout_log": stdout_log,
                "stderr_log": stderr_log,
                "working_directory": working_dir
            }
        )
    
    def _is_dangerous(self, command: str) -> bool:
        """Check if command matches dangerous patterns"""
        command_lower = command.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern.lower() in command_lower:
                return True
        return False
