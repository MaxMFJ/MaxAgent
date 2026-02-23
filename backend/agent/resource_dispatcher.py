"""
Resource Dispatcher - 资源调度器
调度 Cursor、终端等系统资源执行升级任务
"""

import os
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# MacAgent backend 根目录
MACAGENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DispatchTarget(str, Enum):
    """调度目标"""
    CURSOR = "cursor"      # 打开 Cursor 编辑代码
    TERMINAL = "terminal"  # 终端执行命令
    APPLESCRIPT = "applescript"  # AppleScript 控制


@dataclass
class DispatchResult:
    """调度结果"""
    success: bool
    target: DispatchTarget
    output: Optional[str] = None
    error: Optional[str] = None
    pid: Optional[int] = None


class ResourceDispatcher:
    """
    资源调度器 - 调度电脑资源完成升级任务
    
    支持：
    - 打开 Cursor 并指定项目路径/任务
    - 执行终端命令
    - 运行 AppleScript
    """
    
    def __init__(self):
        self._cursor_path = self._find_cursor_app()
    
    def _find_cursor_app(self) -> Optional[str]:
        """查找 Cursor 应用路径"""
        candidates = [
            "/Applications/Cursor.app",
            os.path.expanduser("~/Applications/Cursor.app"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None
    
    async def dispatch_to_cursor(
        self,
        project_path: Optional[str] = None,
        file_path: Optional[str] = None,
        task_prompt: Optional[str] = None
    ) -> DispatchResult:
        """
        调度 Cursor 打开项目/文件
        
        Args:
            project_path: 项目路径，默认 MacAgent 根目录
            file_path: 要打开的具体文件
            task_prompt: 任务描述，写入 .cursor/prompts/upgrade.md 供 AI 参考
        """
        if not self._cursor_path:
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error="未找到 Cursor 应用，请确认已安装 Cursor"
            )
        
        path = project_path or MACAGENT_ROOT
        open_path = file_path or path
        
        try:
            # 如提供任务描述，写入 .cursor/prompts/
            if task_prompt:
                prompts_dir = os.path.join(path, ".cursor", "prompts")
                os.makedirs(prompts_dir, exist_ok=True)
                upgrade_file = os.path.join(prompts_dir, "upgrade.md")
                with open(upgrade_file, "w", encoding="utf-8") as f:
                    f.write(f"# MacAgent 工具升级任务\n\n{task_prompt}")
                logger.info(f"Wrote upgrade task to {upgrade_file}")
            
            # 使用 open 命令打开 Cursor
            cmd = ["open", "-a", "Cursor", open_path]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return DispatchResult(
                    success=True,
                    target=DispatchTarget.CURSOR,
                    output=f"已打开 Cursor: {open_path}",
                    pid=process.pid
                )
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error=stderr.decode() or f"exit code {process.returncode}"
            )
            
        except Exception as e:
            logger.error(f"Dispatch to Cursor failed: {e}")
            return DispatchResult(
                success=False,
                target=DispatchTarget.CURSOR,
                error=str(e)
            )
    
    async def dispatch_to_terminal(
        self,
        command: str,
        working_dir: Optional[str] = None,
        timeout: int = 300
    ) -> DispatchResult:
        """
        调度终端执行命令
        
        Args:
            command: shell 命令
            working_dir: 工作目录
            timeout: 超时秒数
        """
        cwd = working_dir or MACAGENT_ROOT
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return DispatchResult(
                    success=False,
                    target=DispatchTarget.TERMINAL,
                    error=f"命令执行超时 ({timeout}s)"
                )
            
            output = stdout.decode().strip() or stderr.decode().strip()
            return DispatchResult(
                success=(process.returncode == 0),
                target=DispatchTarget.TERMINAL,
                output=output[:2000] if output else None,
                error=None if process.returncode == 0 else stderr.decode()[:500],
                pid=process.pid
            )
            
        except Exception as e:
            logger.error(f"Dispatch to terminal failed: {e}")
            return DispatchResult(
                success=False,
                target=DispatchTarget.TERMINAL,
                error=str(e)
            )
    
    async def run_pip_install(self, package: str) -> DispatchResult:
        """安装 Python 包"""
        venv_pip = os.path.join(MACAGENT_ROOT, "venv", "bin", "pip")
        pip_cmd = venv_pip if os.path.exists(venv_pip) else "pip3"
        return await self.dispatch_to_terminal(
            f"{pip_cmd} install {package}",
            working_dir=MACAGENT_ROOT,
            timeout=120
        )


# 单例
_dispatcher: Optional[ResourceDispatcher] = None


def get_resource_dispatcher() -> ResourceDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = ResourceDispatcher()
    return _dispatcher
