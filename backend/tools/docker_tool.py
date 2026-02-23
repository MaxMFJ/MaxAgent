"""
Docker Tool - 容器管理
"""

import asyncio
import json
from typing import Optional
from .base import BaseTool, ToolResult, ToolCategory


class DockerTool(BaseTool):
    """Docker 容器管理工具"""
    
    name = "docker"
    description = "Docker 容器管理：启动、停止、查看容器和镜像"
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "ps", "images", "start", "stop", "restart", "logs",
                    "run", "exec", "rm", "pull", "build", "compose_up", "compose_down"
                ],
                "description": "Docker 操作"
            },
            "container": {
                "type": "string",
                "description": "容器名称或 ID"
            },
            "image": {
                "type": "string",
                "description": "镜像名称"
            },
            "command": {
                "type": "string",
                "description": "要执行的命令"
            },
            "options": {
                "type": "string",
                "description": "额外选项（如端口映射 -p 8080:80）"
            },
            "compose_file": {
                "type": "string",
                "description": "docker-compose 文件路径"
            },
            "tail": {
                "type": "number",
                "description": "日志行数"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str,
        container: Optional[str] = None,
        image: Optional[str] = None,
        command: Optional[str] = None,
        options: Optional[str] = None,
        compose_file: Optional[str] = None,
        tail: int = 100
    ) -> ToolResult:
        """执行 Docker 操作"""
        
        # 检查 Docker 是否可用
        if not await self._check_docker():
            return ToolResult(success=False, error="Docker 未运行或未安装")
        
        actions = {
            "ps": lambda: self._run_cmd(["docker", "ps", "-a", "--format", "json"]),
            "images": lambda: self._run_cmd(["docker", "images", "--format", "json"]),
            "start": lambda: self._run_cmd(["docker", "start", container]) if container else self._error("需要容器名"),
            "stop": lambda: self._run_cmd(["docker", "stop", container]) if container else self._error("需要容器名"),
            "restart": lambda: self._run_cmd(["docker", "restart", container]) if container else self._error("需要容器名"),
            "logs": lambda: self._get_logs(container, tail),
            "run": lambda: self._run_container(image, options, command),
            "exec": lambda: self._exec_in_container(container, command),
            "rm": lambda: self._run_cmd(["docker", "rm", container]) if container else self._error("需要容器名"),
            "pull": lambda: self._run_cmd(["docker", "pull", image]) if image else self._error("需要镜像名"),
            "build": lambda: self._build_image(image, options),
            "compose_up": lambda: self._compose_up(compose_file),
            "compose_down": lambda: self._compose_down(compose_file),
        }
        
        if action not in actions:
            return ToolResult(success=False, error=f"未知操作: {action}")
        
        return await actions[action]()
    
    async def _check_docker(self) -> bool:
        """检查 Docker 是否可用"""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except FileNotFoundError:
            return False
    
    async def _run_cmd(self, cmd: list) -> ToolResult:
        """执行 Docker 命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(success=False, error=stderr.decode())
            
            output = stdout.decode().strip()
            
            # 尝试解析 JSON 格式输出
            if output and output.startswith('{'):
                lines = output.split('\n')
                data = [json.loads(line) for line in lines if line.strip()]
                return ToolResult(success=True, data=data)
            
            return ToolResult(success=True, data=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    async def _error(self, msg: str) -> ToolResult:
        """返回错误"""
        return ToolResult(success=False, error=msg)
    
    async def _get_logs(self, container: str, tail: int) -> ToolResult:
        """获取容器日志"""
        if not container:
            return ToolResult(success=False, error="需要容器名")
        
        return await self._run_cmd([
            "docker", "logs", "--tail", str(tail), container
        ])
    
    async def _run_container(
        self,
        image: str,
        options: Optional[str],
        command: Optional[str]
    ) -> ToolResult:
        """运行容器"""
        if not image:
            return ToolResult(success=False, error="需要镜像名")
        
        cmd = ["docker", "run", "-d"]
        
        if options:
            cmd.extend(options.split())
        
        cmd.append(image)
        
        if command:
            cmd.extend(command.split())
        
        return await self._run_cmd(cmd)
    
    async def _exec_in_container(self, container: str, command: str) -> ToolResult:
        """在容器中执行命令"""
        if not container or not command:
            return ToolResult(success=False, error="需要容器名和命令")
        
        cmd = ["docker", "exec", container] + command.split()
        return await self._run_cmd(cmd)
    
    async def _build_image(self, image: str, options: Optional[str]) -> ToolResult:
        """构建镜像"""
        if not image:
            return ToolResult(success=False, error="需要镜像名")
        
        cmd = ["docker", "build", "-t", image]
        
        if options:
            cmd.extend(options.split())
        else:
            cmd.append(".")
        
        return await self._run_cmd(cmd)
    
    async def _compose_up(self, compose_file: Optional[str]) -> ToolResult:
        """docker-compose up"""
        cmd = ["docker-compose"]
        
        if compose_file:
            cmd.extend(["-f", compose_file])
        
        cmd.extend(["up", "-d"])
        
        return await self._run_cmd(cmd)
    
    async def _compose_down(self, compose_file: Optional[str]) -> ToolResult:
        """docker-compose down"""
        cmd = ["docker-compose"]
        
        if compose_file:
            cmd.extend(["-f", compose_file])
        
        cmd.append("down")
        
        return await self._run_cmd(cmd)
