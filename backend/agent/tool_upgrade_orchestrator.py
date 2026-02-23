"""
Tool Upgrade Orchestrator - 工具自我升级编排器
当任务无法执行时，LLM 规划升级方案并调度资源完成
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator, Callable, List, Union
from dataclasses import dataclass, field
from enum import Enum

from .llm_client import LLMClient
from .resource_dispatcher import get_resource_dispatcher, DispatchTarget, DispatchResult

logger = logging.getLogger(__name__)

# 升级任务规划 prompt
UPGRADE_PLAN_PROMPT = """你是一个 MacAgent 工具升级规划师。用户请求的功能无法被当前工具满足，需要创建新工具或修改现有工具。

当前无法执行的原因：{reason}
用户原始请求：{user_message}

可选执行方式：
1. **terminal** - 适合：安装依赖(pip install)、创建文件、执行脚本
2. **cursor** - 适合：需要编写/修改 Python 代码、创建新工具文件

请分析需求，返回 JSON 格式的升级计划：

{{
  "action": "terminal" 或 "cursor" 或 "both",
  "steps": [
    {{
      "target": "terminal" 或 "cursor",
      "description": "步骤描述",
      "command": "终端命令（仅 terminal 时）",
      "task_prompt": "给 Cursor AI 的任务描述（仅 cursor 时）"
    }}
  ],
  "tool_spec": {{
    "name": "新工具名称（如 xxx_tool）",
    "description": "工具描述",
    "action": "主要操作类型"
  }},
  "summary": "简要说明升级方案",
  "restart_required": false
}}

restart_required: 仅当安装了新的 Python 包(pip install)或修改了核心代码必须重启时设为 true。
只返回 JSON，不要其他文字。"""


@dataclass
class UpgradePlan:
    """升级计划"""
    action: str  # terminal, cursor, both
    steps: List[Dict[str, Any]]
    tool_spec: Dict[str, Any]
    summary: str
    restart_required: bool = False


class UpgradeOrchestrator:
    """
    工具升级编排器
    
    流程：
    1. 接收无法执行的原因 + 用户请求
    2. LLM 规划升级步骤
    3. 广播升级状态
    4. 调度资源执行
    5. 完成后通知（动态加载或重启）
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        on_status_change: Optional[Callable[..., Any]] = None,
        on_broadcast: Optional[Callable[..., Any]] = None,
        on_load_generated_tools: Optional[Callable[[], Any]] = None,
        on_trigger_restart: Optional[Callable[[], Any]] = None
    ):
        self.llm = llm_client
        self.dispatcher = get_resource_dispatcher()
        self.on_status_change = on_status_change  # (status, message) -> None | Awaitable
        self.on_broadcast = on_broadcast  # (message_dict) -> None | Awaitable
        self.on_load_generated_tools = on_load_generated_tools  # () -> List[str]
        self.on_trigger_restart = on_trigger_restart  # () -> Awaitable
        self._upgrading = False
    
    async def _broadcast(self, msg: dict):
        """广播消息给所有客户端"""
        if self.on_broadcast:
            try:
                result = self.on_broadcast(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Broadcast failed: {e}")
    
    async def _set_status(self, status: str, message: str = ""):
        """更新状态并广播"""
        if self.on_status_change:
            try:
                result = self.on_status_change(status, message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Status change callback failed: {e}")
        await self._broadcast({
            "type": "status_change",
            "status": status,
            "message": message,
            "timestamp": __import__("datetime").datetime.now().isoformat()
        })
    
    async def _broadcast_content(self, content: str):
        """下发系统消息给用户"""
        await self._broadcast({
            "type": "content",
            "content": content,
            "is_system": True
        })
    
    def _parse_plan(self, llm_response: str) -> Optional[UpgradePlan]:
        """解析 LLM 返回的 JSON 计划"""
        try:
            # 提取 JSON 块
            text = llm_response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(text)
            return UpgradePlan(
                action=data.get("action", "terminal"),
                steps=data.get("steps", []),
                tool_spec=data.get("tool_spec", {}),
                summary=data.get("summary", ""),
                restart_required=data.get("restart_required", False)
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse upgrade plan: {e}")
            return None
    
    async def plan_upgrade(
        self,
        reason: str,
        user_message: str
    ) -> Optional[UpgradePlan]:
        """使用 LLM 规划升级方案"""
        messages = [
            {
                "role": "system",
                "content": "你是一个技术规划师，输出严格的 JSON 格式。"
            },
            {
                "role": "user",
                "content": UPGRADE_PLAN_PROMPT.format(
                    reason=reason,
                    user_message=user_message
                )
            }
        ]
        
        try:
            response = await self.llm.chat(messages, tools=None)
            content = response.get("content", "")
            return self._parse_plan(content)
        except Exception as e:
            logger.error(f"LLM plan failed: {e}")
            return None
    
    async def execute_upgrade(
        self,
        reason: str,
        user_message: str,
        session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行完整升级流程
        
        Yields:
            进度更新 dict，包含 type, phase, detail 等
        """
        if self._upgrading:
            yield {"type": "upgrade_error", "error": "已有升级任务在执行中"}
            return
        
        self._upgrading = True
        try:
            # 1. 广播升级状态
            await self._set_status("upgrading", "正在分析升级方案...")
            await self._broadcast_content("🔧 系统正在升级以支持您请求的功能，请稍候...")
            yield {"type": "upgrade_progress", "phase": "planning", "detail": "分析中"}
            
            # 2. LLM 规划
            plan = await self.plan_upgrade(reason, user_message)
            if not plan:
                await self._set_status("normal", "升级规划失败")
                yield {"type": "upgrade_error", "error": "无法生成升级方案"}
                return
            
            yield {"type": "upgrade_progress", "phase": "planned", "plan": plan.summary}
            await self._set_status("upgrading", plan.summary)
            
            # 3. 执行步骤
            for i, step in enumerate(plan.steps):
                target = step.get("target", "terminal")
                yield {"type": "upgrade_progress", "phase": "executing", "step": i + 1, "target": target}
                
                if target == "terminal" and step.get("command"):
                    result = await self.dispatcher.dispatch_to_terminal(step["command"])
                    yield {
                        "type": "upgrade_step_result",
                        "target": "terminal",
                        "success": result.success,
                        "output": result.output,
                        "error": result.error
                    }
                    if not result.success:
                        logger.warning(f"Terminal step failed: {result.error}")
                
                elif target == "cursor" and step.get("task_prompt"):
                    result = await self.dispatcher.dispatch_to_cursor(
                        task_prompt=step["task_prompt"]
                    )
                    yield {
                        "type": "upgrade_step_result",
                        "target": "cursor",
                        "success": result.success,
                        "error": result.error
                    }
                    if not result.success:
                        logger.warning(f"Cursor step failed: {result.error}")
            
            # 4. 动态加载新工具（无需重启）
            tool_name = plan.tool_spec.get("name", "")
            loaded_tools: List[str] = []
            if self.on_load_generated_tools:
                yield {"type": "upgrade_progress", "phase": "reloading", "detail": "正在加载新工具..."}
                try:
                    result = self.on_load_generated_tools()
                    loaded_tools = list(result) if result else []
                    if loaded_tools:
                        await self._broadcast_content(
                            f"✅ 已动态加载新工具: {', '.join(loaded_tools)}，可立即使用"
                        )
                except Exception as e:
                    logger.warning(f"Dynamic load failed: {e}")
            
            # 5. 若计划要求重启（如 pip install 了新依赖），触发重启流程
            plan_restart = plan.restart_required
            if plan_restart and self.on_trigger_restart:
                yield {"type": "upgrade_progress", "phase": "restarting", "detail": "准备重启服务"}
                result = self.on_trigger_restart()
                if asyncio.iscoroutine(result):
                    await result
            else:
                await self._set_status("normal", "升级完成")
                if not loaded_tools and tool_name:
                    await self._broadcast_content(
                        "✅ 升级流程已完成。若添加了新工具文件至 tools/generated/，"
                        "请调用 POST /tools/reload 或重启服务以生效。"
                    )
                elif not loaded_tools:
                    await self._broadcast_content("✅ 升级流程已完成。")
            
            yield {"type": "upgrade_complete", "plan": plan.summary, "loaded_tools": loaded_tools}
            
        except Exception as e:
            logger.error(f"Upgrade execution failed: {e}")
            await self._set_status("normal", f"升级失败: {str(e)}")
            await self._broadcast_content(f"❌ 升级过程中出错: {str(e)}")
            yield {"type": "upgrade_error", "error": str(e)}
        
        finally:
            self._upgrading = False


# 单例（需在 main.py 中注入 callbacks）
_orchestrator: Optional[UpgradeOrchestrator] = None


def get_upgrade_orchestrator(
    llm_client: Optional[LLMClient] = None,
    on_status_change: Optional[Callable[[str, str], Any]] = None,
    on_broadcast: Optional[Callable[[dict], Any]] = None,
    on_load_generated_tools: Optional[Callable[[], Any]] = None,
    on_trigger_restart: Optional[Callable[[], Any]] = None
) -> UpgradeOrchestrator:
    """获取升级编排器单例，需传入 llm_client 和回调"""
    global _orchestrator
    if _orchestrator is None:
        if not llm_client:
            raise ValueError("llm_client is required for UpgradeOrchestrator")
        _orchestrator = UpgradeOrchestrator(
            llm_client,
            on_status_change=on_status_change,
            on_broadcast=on_broadcast,
            on_load_generated_tools=on_load_generated_tools,
            on_trigger_restart=on_trigger_restart
        )
    else:
        if on_status_change is not None:
            _orchestrator.on_status_change = on_status_change
        if on_broadcast is not None:
            _orchestrator.on_broadcast = on_broadcast
        if on_load_generated_tools is not None:
            _orchestrator.on_load_generated_tools = on_load_generated_tools
        if on_trigger_restart is not None:
            _orchestrator.on_trigger_restart = on_trigger_restart
    return _orchestrator
