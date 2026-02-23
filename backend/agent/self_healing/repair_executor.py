"""
修复执行器 - 执行修复动作

负责：
1. 执行修复计划中的动作
2. 管理执行状态
3. 处理回滚
4. 记录执行日志
"""

import os
import json
import asyncio
import logging
import subprocess
import tempfile
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

from .repair_planner import RepairPlan, RepairAction, ActionType

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class ActionExecutionResult:
    """单个动作的执行结果"""
    action: RepairAction
    status: ExecutionStatus
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action.action_type.value,
            "description": self.action.description,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class ExecutionResult:
    """完整执行结果"""
    plan: RepairPlan
    status: ExecutionStatus
    action_results: List[ActionExecutionResult] = field(default_factory=list)
    total_duration_ms: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS
    
    @property
    def failed_actions(self) -> List[ActionExecutionResult]:
        return [r for r in self.action_results if r.status == ExecutionStatus.FAILED]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_strategy": self.plan.strategy.value,
            "status": self.status.value,
            "action_results": [r.to_dict() for r in self.action_results],
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success
        }


class RepairExecutor:
    """修复执行器"""
    
    def __init__(
        self,
        config_manager: Optional[Any] = None,
        api_client: Optional[Any] = None,
        dry_run: bool = False
    ):
        """
        初始化执行器
        
        Args:
            config_manager: 配置管理器
            api_client: API 客户端
            dry_run: 是否只模拟执行（不实际修改）
        """
        self.config_manager = config_manager
        self.api_client = api_client
        self.dry_run = dry_run
        self.execution_history: List[ExecutionResult] = []
        
        # 动作执行器映射
        self._executors: Dict[ActionType, Callable] = {
            ActionType.EXECUTE_SCRIPT: self._execute_script,
            ActionType.MODIFY_FILE: self._modify_file,
            ActionType.CALL_API: self._call_api,
            ActionType.CHANGE_CONFIG: self._change_config,
            ActionType.RESTART_PROCESS: self._restart_process,
            ActionType.SEND_NOTIFICATION: self._send_notification,
        }
    
    async def execute(self, plan: RepairPlan) -> ExecutionResult:
        """
        执行修复计划
        
        Args:
            plan: 修复计划
        
        Returns:
            ExecutionResult: 执行结果
        """
        result = ExecutionResult(
            plan=plan,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now()
        )
        
        logger.info(f"Starting repair execution: {plan.strategy.value}")
        
        try:
            for action in plan.actions:
                action_result = await self._execute_action(action)
                result.action_results.append(action_result)
                
                # 如果动作失败，决定是否继续
                if action_result.status == ExecutionStatus.FAILED:
                    # 尝试回滚
                    if action.rollback_action:
                        await self._execute_action(action.rollback_action)
                    
                    # 如果是关键动作失败，停止执行
                    if self._is_critical_action(action):
                        result.status = ExecutionStatus.FAILED
                        break
            
            # 判断整体结果
            if result.status == ExecutionStatus.RUNNING:
                failed_count = len(result.failed_actions)
                if failed_count == 0:
                    result.status = ExecutionStatus.SUCCESS
                elif failed_count < len(plan.actions) / 2:
                    result.status = ExecutionStatus.SUCCESS  # 部分成功视为成功
                else:
                    result.status = ExecutionStatus.FAILED
        
        except Exception as e:
            logger.error(f"Execution failed with exception: {e}")
            result.status = ExecutionStatus.FAILED
            result.action_results.append(ActionExecutionResult(
                action=RepairAction(
                    action_type=ActionType.SEND_NOTIFICATION,
                    description="执行异常"
                ),
                status=ExecutionStatus.FAILED,
                error=str(e)
            ))
        
        finally:
            result.completed_at = datetime.now()
            result.total_duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
            self.execution_history.append(result)
        
        logger.info(f"Repair execution completed: {result.status.value}")
        return result
    
    async def _execute_action(self, action: RepairAction) -> ActionExecutionResult:
        """执行单个动作"""
        start_time = datetime.now()
        
        logger.info(f"Executing action: {action.action_type.value} - {action.description}")
        
        if self.dry_run:
            return ActionExecutionResult(
                action=action,
                status=ExecutionStatus.SKIPPED,
                output="[DRY RUN] Action skipped",
                duration_ms=0
            )
        
        executor = self._executors.get(action.action_type)
        if not executor:
            return ActionExecutionResult(
                action=action,
                status=ExecutionStatus.FAILED,
                error=f"No executor for action type: {action.action_type.value}"
            )
        
        try:
            # 执行动作，支持重试
            last_error = ""
            for attempt in range(action.retry_count):
                try:
                    output = await asyncio.wait_for(
                        executor(action),
                        timeout=action.timeout_seconds
                    )
                    
                    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    
                    return ActionExecutionResult(
                        action=action,
                        status=ExecutionStatus.SUCCESS,
                        output=output,
                        duration_ms=duration_ms
                    )
                
                except asyncio.TimeoutError:
                    last_error = f"Action timed out after {action.timeout_seconds}s"
                except Exception as e:
                    last_error = str(e)
                
                if attempt < action.retry_count - 1:
                    await asyncio.sleep(1)  # 重试前等待
            
            # 所有重试都失败
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return ActionExecutionResult(
                action=action,
                status=ExecutionStatus.FAILED,
                error=last_error,
                duration_ms=duration_ms
            )
        
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            return ActionExecutionResult(
                action=action,
                status=ExecutionStatus.FAILED,
                error=str(e),
                duration_ms=duration_ms
            )
    
    async def _execute_script(self, action: RepairAction) -> str:
        """执行脚本"""
        params = action.parameters
        script_type = params.get("script_type", "python")
        script_content = params.get("script_content", "")
        
        if not script_content:
            raise ValueError("Script content is empty")
        
        # 创建临时脚本文件
        suffix = {
            "python": ".py",
            "bash": ".sh",
            "javascript": ".js"
        }.get(script_type, ".py")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # 执行脚本
            if script_type == "python":
                cmd = ["python", script_path]
            elif script_type == "bash":
                cmd = ["bash", script_path]
            elif script_type == "javascript":
                cmd = ["node", script_path]
            else:
                cmd = ["python", script_path]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"Script failed: {stderr.decode()}")
            
            return stdout.decode()
        
        finally:
            # 清理临时文件
            os.unlink(script_path)
    
    async def _modify_file(self, action: RepairAction) -> str:
        """修改文件"""
        params = action.parameters
        file_path = params.get("file_path")
        modifications = params.get("modifications", [])
        
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # 备份原文件
        backup_path = f"{file_path}.backup"
        with open(file_path, 'r') as f:
            original_content = f.read()
        
        with open(backup_path, 'w') as f:
            f.write(original_content)
        
        try:
            # 应用修改
            content = original_content
            for mod in modifications:
                old_text = mod.get("old")
                new_text = mod.get("new")
                if old_text and new_text:
                    content = content.replace(old_text, new_text)
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            return f"Modified {file_path}, backup at {backup_path}"
        
        except Exception as e:
            # 恢复备份
            with open(file_path, 'w') as f:
                f.write(original_content)
            raise e
    
    async def _call_api(self, action: RepairAction) -> str:
        """调用 API"""
        params = action.parameters
        endpoint = params.get("endpoint", "")
        method = params.get("method", "GET")
        body = params.get("body", {})
        
        # 使用 httpx 或 requests 调用 API
        import httpx
        
        base_url = "http://127.0.0.1:8765"
        url = f"{base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        
        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                response = await client.get(url)
            elif method.upper() == "POST":
                response = await client.post(url, json=body)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return response.text
    
    async def _change_config(self, action: RepairAction) -> str:
        """修改配置"""
        params = action.parameters
        config_key = params.get("config_key")
        new_value = params.get("new_value")
        
        if not config_key:
            raise ValueError("Config key is required")
        
        # 通过 API 更新配置
        result = await self._call_api(RepairAction(
            action_type=ActionType.CALL_API,
            description="Update config",
            parameters={
                "endpoint": "/config",
                "method": "POST",
                "body": {config_key: new_value}
            }
        ))
        
        return f"Config updated: {config_key} = {new_value}"
    
    async def _restart_process(self, action: RepairAction) -> str:
        """重启进程"""
        params = action.parameters
        service = params.get("service", "backend")
        wait_seconds = params.get("wait_seconds", 5)
        
        if service == "backend":
            # 重启后端服务
            process = await asyncio.create_subprocess_shell(
                'pkill -f "python.*main.py" 2>/dev/null; sleep 2; cd /Users/lzz/Desktop/未命名文件夹/MacAgent/backend && python main.py &',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        
        elif service == "ollama":
            process = await asyncio.create_subprocess_shell(
                'pkill ollama 2>/dev/null; sleep 2; ollama serve &',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        
        # 等待服务启动
        await asyncio.sleep(wait_seconds)
        
        return f"Service {service} restarted"
    
    async def _send_notification(self, action: RepairAction) -> str:
        """发送通知"""
        params = action.parameters
        message = params.get("message", "Notification")
        severity = params.get("severity", "INFO")
        
        # 使用 macOS 通知
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e",
                f'display notification "{message}" with title "MacAgent Self-Healing" subtitle "{severity}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
        
        logger.info(f"Notification: [{severity}] {message}")
        return f"Notification sent: {message}"
    
    def _is_critical_action(self, action: RepairAction) -> bool:
        """判断是否是关键动作"""
        critical_types = {
            ActionType.MODIFY_FILE,
            ActionType.RESTART_PROCESS,
        }
        return action.action_type in critical_types
    
    def get_execution_history(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return [r.to_dict() for r in self.execution_history[-count:]]


# 全局实例
_repair_executor: Optional[RepairExecutor] = None


def get_repair_executor(dry_run: bool = False) -> RepairExecutor:
    """获取修复执行器单例"""
    global _repair_executor
    if _repair_executor is None:
        _repair_executor = RepairExecutor(dry_run=dry_run)
    return _repair_executor
