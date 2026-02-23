"""
Script Execution Tool
Create and execute scripts in various languages (Python, Bash, JavaScript)
"""

import asyncio
import os
import tempfile
import shutil
from typing import Any, Dict, Optional
from datetime import datetime

from .base import BaseTool, ToolResult, ToolCategory


class ScriptTool(BaseTool):
    """Tool for creating and executing scripts"""
    
    name = "script"
    description = """脚本创建和执行工具。
支持功能：
- 创建 Python、Bash、JavaScript 脚本
- 在安全目录内执行脚本
- 捕获输出和错误
- 支持保存脚本到指定路径

支持的语言：
- python: Python 3 脚本
- bash/shell: Bash 脚本
- javascript/node: Node.js 脚本"""
    
    parameters = {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "description": "脚本语言: python, bash, shell, javascript, node",
                "enum": ["python", "bash", "shell", "javascript", "node"]
            },
            "code": {
                "type": "string",
                "description": "要执行的脚本代码"
            },
            "run": {
                "type": "boolean",
                "description": "是否执行脚本（默认 True）",
                "default": True
            },
            "save_path": {
                "type": "string",
                "description": "保存脚本的路径（可选）"
            },
            "working_directory": {
                "type": "string",
                "description": "脚本执行的工作目录"
            },
            "timeout": {
                "type": "integer",
                "description": "执行超时时间（秒），默认 120",
                "default": 120
            },
            "args": {
                "type": "array",
                "description": "传递给脚本的参数",
                "items": {"type": "string"}
            }
        },
        "required": ["language", "code"]
    }
    
    category = ToolCategory.TERMINAL
    requires_confirmation = False
    
    LANGUAGE_CONFIG = {
        "python": {
            "extension": ".py",
            "runner": ["python3"],
            "shebang": "#!/usr/bin/env python3"
        },
        "bash": {
            "extension": ".sh",
            "runner": ["bash"],
            "shebang": "#!/bin/bash"
        },
        "shell": {
            "extension": ".sh",
            "runner": ["bash"],
            "shebang": "#!/bin/bash"
        },
        "javascript": {
            "extension": ".js",
            "runner": ["node"],
            "shebang": "#!/usr/bin/env node"
        },
        "node": {
            "extension": ".js",
            "runner": ["node"],
            "shebang": "#!/usr/bin/env node"
        }
    }
    
    SAFE_DIRS = [
        os.path.expanduser("~"),
        "/tmp",
        "/var/tmp"
    ]
    
    async def execute(self, **kwargs) -> ToolResult:
        language = kwargs.get("language", "").lower()
        code = kwargs.get("code", "")
        should_run = kwargs.get("run", True)
        save_path = kwargs.get("save_path")
        working_dir = kwargs.get("working_directory", os.path.expanduser("~"))
        timeout = kwargs.get("timeout", 120)
        args = kwargs.get("args", [])
        
        if not code:
            return ToolResult(success=False, error="代码不能为空")
        
        if language not in self.LANGUAGE_CONFIG:
            return ToolResult(
                success=False,
                error=f"不支持的语言: {language}. 支持: {list(self.LANGUAGE_CONFIG.keys())}"
            )
        
        config = self.LANGUAGE_CONFIG[language]
        
        working_dir = os.path.expanduser(working_dir)
        if not self._is_safe_path(working_dir):
            return ToolResult(
                success=False,
                error=f"工作目录不在安全范围内: {working_dir}"
            )
        
        try:
            if save_path:
                script_path = os.path.expanduser(save_path)
                if not self._is_safe_path(script_path):
                    return ToolResult(
                        success=False,
                        error=f"保存路径不在安全范围内: {script_path}"
                    )
                
                os.makedirs(os.path.dirname(script_path), exist_ok=True)
                
                with open(script_path, "w", encoding="utf-8") as f:
                    if not code.startswith("#!"):
                        f.write(config["shebang"] + "\n")
                    f.write(code)
                
                os.chmod(script_path, 0o755)
                
                if not should_run:
                    return ToolResult(
                        success=True,
                        data={
                            "action": "saved",
                            "path": script_path,
                            "language": language
                        }
                    )
            else:
                fd, script_path = tempfile.mkstemp(
                    suffix=config["extension"],
                    dir=working_dir
                )
                
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    if not code.startswith("#!"):
                        f.write(config["shebang"] + "\n")
                    f.write(code)
                
                os.chmod(script_path, 0o755)
            
            if not should_run:
                return ToolResult(
                    success=True,
                    data={
                        "action": "created",
                        "path": script_path,
                        "language": language
                    }
                )
            
            cmd = config["runner"] + [script_path] + args
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
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
                
                if not save_path:
                    try:
                        os.unlink(script_path)
                    except:
                        pass
                
                return ToolResult(
                    success=False,
                    error=f"脚本执行超时（{timeout}秒）",
                    data={"timeout": timeout, "path": script_path}
                )
            
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()
            
            if not save_path:
                try:
                    os.unlink(script_path)
                except:
                    pass
            
            return ToolResult(
                success=process.returncode == 0,
                data={
                    "exit_code": process.returncode,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "language": language,
                    "path": script_path if save_path else None
                },
                error=stderr_str if process.returncode != 0 else None
            )
            
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=f"找不到运行时: {config['runner'][0]}"
            )
        except PermissionError:
            return ToolResult(success=False, error="权限不足，无法执行脚本")
        except Exception as e:
            return ToolResult(success=False, error=f"脚本执行错误: {str(e)}")
    
    def _is_safe_path(self, path: str) -> bool:
        """Check if path is within safe directories"""
        path = os.path.abspath(os.path.expanduser(path))
        
        for safe_dir in self.SAFE_DIRS:
            safe_dir = os.path.abspath(os.path.expanduser(safe_dir))
            if path.startswith(safe_dir):
                return True
        
        return False


class MultiScriptTool(BaseTool):
    """Tool for executing multiple scripts in sequence"""
    
    name = "multi_script"
    description = """批量脚本执行工具。
支持按顺序执行多个脚本，并收集所有结果。
适用于需要多步骤脚本处理的任务。"""
    
    parameters = {
        "type": "object",
        "properties": {
            "scripts": {
                "type": "array",
                "description": "要执行的脚本列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "language": {"type": "string"},
                        "code": {"type": "string"},
                        "name": {"type": "string", "description": "脚本名称（可选）"}
                    },
                    "required": ["language", "code"]
                }
            },
            "working_directory": {
                "type": "string",
                "description": "工作目录"
            },
            "stop_on_error": {
                "type": "boolean",
                "description": "遇到错误时是否停止（默认 True）",
                "default": True
            }
        },
        "required": ["scripts"]
    }
    
    category = ToolCategory.TERMINAL
    requires_confirmation = False
    
    async def execute(self, **kwargs) -> ToolResult:
        scripts = kwargs.get("scripts", [])
        working_dir = kwargs.get("working_directory", os.path.expanduser("~"))
        stop_on_error = kwargs.get("stop_on_error", True)
        
        if not scripts:
            return ToolResult(success=False, error="没有提供脚本")
        
        script_tool = ScriptTool()
        results = []
        all_success = True
        
        for i, script in enumerate(scripts):
            script_name = script.get("name", f"script_{i+1}")
            
            result = await script_tool.execute(
                language=script.get("language", "python"),
                code=script.get("code", ""),
                working_directory=working_dir
            )
            
            results.append({
                "name": script_name,
                "success": result.success,
                "output": result.data.get("stdout") if result.data else None,
                "error": result.error
            })
            
            if not result.success:
                all_success = False
                if stop_on_error:
                    break
        
        return ToolResult(
            success=all_success,
            data={
                "total_scripts": len(scripts),
                "executed": len(results),
                "results": results
            },
            error=None if all_success else "部分脚本执行失败"
        )
