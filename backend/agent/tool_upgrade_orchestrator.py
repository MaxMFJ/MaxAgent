"""
Tool Upgrade Orchestrator - 工具自我升级编排器
当任务无法执行时，LLM 规划升级方案并调度资源完成
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator, Callable, List, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .llm_client import LLMClient
from .resource_dispatcher import get_resource_dispatcher, DispatchTarget, DispatchResult, MACAGENT_ROOT

logger = logging.getLogger(__name__)

# 升级任务规划 prompt
UPGRADE_PLAN_PROMPT = """你是一个 MacAgent 工具升级规划师。用户请求的功能无法被当前工具满足，或 Agent 行为需要优化。

**两类升级**：
1. **新工具**：需要新能力 → 创建 tools/generated/xxx_tool.py
2. **Agent 规则**：Agent 行为有问题（如重复创建、无效循环）→ 追加规则到 core 的进化规则

当前无法执行的原因：{reason}
用户原始请求：{user_message}

**项目根目录（backend）绝对路径**：`{macagent_root}` — terminal 命令将在此目录执行，请使用此路径或相对路径（如 tools/generated/），不要使用其他路径。

可选执行方式：
1. **terminal** - 适合：pip install 第三方包（注意：smtplib、email、ssl、json、os 等是 Python 标准库，不要 pip install）
2. **cursor** - 适合：创建新工具（必须用于编写 Python 工具代码）

请分析需求，返回 JSON 格式的升级计划：

{{
  "action": "terminal" 或 "cursor" 或 "both",
  "steps": [
    {{
      "target": "terminal" 或 "cursor",
      "description": "步骤描述",
      "command": "终端命令（仅 terminal 时）",
      "task_prompt": "给 Cursor 的详细任务（仅 cursor 时，需说明实现逻辑、参数、调用方式）"
    }}
  ],
  "tool_spec": {{
    "name": "工具名，用于 LLM 调用，如 tunnel_monitor",
    "file_name": "文件名，必须为 xxx_tool.py，如 tunnel_monitor_tool.py",
    "description": "工具描述，供 LLM 理解能力",
    "parameters": {{"type":"object","properties":{{}},"required":[]}},
    "category": "system 或 application 或 custom"
  }},
  "summary": "简要说明升级方案",
  "restart_required": false,
  "core_rules_add": []
}}

**core_rules_add**（可选）：当问题是 Agent 行为（如重复创建文件、无效循环）时，添加规则。每项为一条 Markdown 规则，如 ["- 若文件已存在且内容满足需求，直接说明用法，不要重复创建"]
**重要**：tool_spec.file_name 必须为 `xxx_tool.py` 格式。新工具文件必须创建在 MacAgent 项目的 backend/tools/generated/ 目录，严禁创建在 ~/、$HOME 等用户目录。restart_required 仅当 pip install 或修改核心代码时设为 true。
只返回 JSON，不要其他文字。"""


@dataclass
class UpgradePlan:
    """升级计划"""
    action: str  # terminal, cursor, both
    steps: List[Dict[str, Any]]
    tool_spec: Dict[str, Any]
    summary: str
    restart_required: bool = False
    core_rules_add: List[str] = field(default_factory=list)  # Agent 进化规则


# Cursor 任务模板：强制输出到 tools/generated/，继承 BaseTool
CURSOR_TASK_HEADER = """
## ⚠️ 强制性要求（必须遵守，违反则升级失败）

1. **输出路径（硬性）**：
   - 必须在 MacAgent 项目内创建：`tools/generated/{file_name}`（相对 workspace 根 backend/）
   - 绝对路径示例：`{absolute_output_path}`
   - **严禁**创建在：~/、$HOME、/tmp、/Users/xxx/、桌面 等项目外路径
   - 只有 tools/generated/ 下的工具会被 Agent 动态加载
2. **类结构**：必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
3. **必须实现**：`name`、`description`、`parameters`（JSON Schema）、`execute()` 异步方法

## 工具代码模板参考

```python
from tools.base import BaseTool, ToolResult, ToolCategory

class {class_name}(BaseTool):
    name = "{tool_name}"
    description = "{tool_description}"
    category = ToolCategory.{category}
    parameters = {parameters_json}

    async def execute(self, **kwargs) -> ToolResult:
        # 实现逻辑
        return ToolResult(success=True, data={{...}})
```

## 你的具体任务
"""

# LLM 自主生成工具代码的 prompt（不依赖 Cursor）
LLM_TOOL_GEN_PROMPT = """你是一个 Python 工具开发专家。根据以下规格生成完整的 MacAgent 工具代码。

**规格**：
{task_description}

**约束**：
1. 必须继承 `from tools.base import BaseTool, ToolResult, ToolCategory`
2. 实现 name, description, parameters (JSON Schema), async def execute(**kwargs) -> ToolResult
3. 使用 asyncio.create_subprocess_shell 或 create_subprocess_exec 执行命令，禁止使用 subprocess.run、subprocess.Popen
4. smtplib、email、ssl 是 Python 标准库，直接 import 即可，不要 pip install
5. **工具必须自包含**：逻辑写在 Python 代码内，禁止生成调用 ~/、$HOME、用户目录下脚本的代码；禁止在代码中写入或依赖用户主目录的 .sh 等脚本
6. 输出文件将由系统写入 tools/generated/，你只需输出完整 Python 代码，不要解释，不要 markdown 标记之外的任何文字

请输出完整的工具代码："""


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
        on_trigger_restart: Optional[Callable[[], Any]] = None,
        on_git_checkpoint: Optional[Callable[[], tuple]] = None,
        on_git_rollback: Optional[Callable[[], tuple]] = None
    ):
        self.llm = llm_client
        self.dispatcher = get_resource_dispatcher()
        self.on_status_change = on_status_change
        self.on_broadcast = on_broadcast
        self.on_load_generated_tools = on_load_generated_tools
        self.on_trigger_restart = on_trigger_restart
        self.on_git_checkpoint = on_git_checkpoint  # () -> (success, message)
        self.on_git_rollback = on_git_rollback  # () -> (success, message)
        self._upgrading = False
    
    def update_llm(self, llm_client: LLMClient) -> None:
        """更新 LLM 客户端（配置同步时调用，与 AgentCore 保持一致）"""
        self.llm = llm_client
    
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
    
    async def _generate_tool_via_llm(self, step: Dict[str, Any], plan: UpgradePlan) -> Tuple[bool, str, Optional[str]]:
        """
        LLM 自主生成工具代码并写入 tools/generated/
        返回 (success, error_message, output_path)
        """
        try:
            from agent.upgrade_security import check_code_safety, is_path_allowed
        except ImportError:
            check_code_safety = lambda c: (True, "")
            is_path_allowed = lambda p: True
        
        spec = plan.tool_spec
        file_name = spec.get("file_name", "") or (spec.get("name", "new_tool").replace("-", "_") + "_tool.py")
        if not file_name.endswith(".py"):
            file_name = file_name.rstrip("_") + "_tool.py"
        output_path = os.path.join(MACAGENT_ROOT, "tools", "generated", file_name)
        
        task_desc = self._build_cursor_task(step, plan)
        prompt = LLM_TOOL_GEN_PROMPT.format(task_description=task_desc)
        
        try:
            response = await self.llm.chat([
                {"role": "system", "content": "你输出完整的 Python 代码，仅代码，无其他文字。"},
                {"role": "user", "content": prompt}
            ], tools=None)
            content = response.get("content", "").strip()
            
            # 提取 ```python ... ``` 块
            if "```python" in content:
                content = content.split("```python")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            if not content or "from tools.base" not in content:
                return False, "LLM 未返回有效的工具代码", None
            
            safe, err = check_code_safety(content)
            if not safe:
                return False, f"安全校验失败: {err}", None
            
            if not is_path_allowed(output_path):
                return False, f"路径不在允许范围: {output_path}", None
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"LLM generated tool: {output_path}")
            return True, "", output_path
        except Exception as e:
            logger.error(f"LLM tool generation failed: {e}")
            return False, str(e), None
    
    def _build_cursor_task(self, step: Dict[str, Any], plan: UpgradePlan) -> str:
        """构建 Cursor 的完整任务描述，包含强制约束与模板"""
        task_prompt = step.get("task_prompt", "")
        spec = plan.tool_spec
        file_name = spec.get("file_name", "") or (spec.get("name", "new_tool") + "_tool.py")
        if not file_name.endswith(".py"):
            file_name = file_name.rstrip("_") + "_tool.py"
        absolute_output_path = os.path.join(MACAGENT_ROOT, "tools", "generated", file_name)
        tool_name = spec.get("name", "new_tool").replace("-", "_")
        tool_description = spec.get("description", "新工具")
        params = spec.get("parameters") or {"type": "object", "properties": {}, "required": []}
        category = (spec.get("category") or "CUSTOM").upper()
        if category not in ("SYSTEM", "APPLICATION", "FILE", "TERMINAL", "CLIPBOARD", "BROWSER", "CUSTOM"):
            category = "CUSTOM"
        class_name = "".join(w.capitalize() for w in file_name.replace(".py", "").split("_"))
        params_json = json.dumps(params, ensure_ascii=False, indent=4)
        header = CURSOR_TASK_HEADER.format(
            file_name=file_name,
            absolute_output_path=absolute_output_path,
            class_name=class_name,
            tool_name=tool_name,
            tool_description=tool_description,
            category=category,
            parameters_json=params_json,
        )
        return header + "\n" + task_prompt

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
                restart_required=data.get("restart_required", False),
                core_rules_add=data.get("core_rules_add") or []
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
                    user_message=user_message,
                    macagent_root=MACAGENT_ROOT
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
            
            # 2.3 应用 Agent 进化规则（若有）
            if plan.core_rules_add:
                rules_path = os.path.join(MACAGENT_ROOT, "data", "agent_evolved_rules.md")
                try:
                    existing = ""
                    if os.path.exists(rules_path):
                        with open(rules_path, "r", encoding="utf-8") as f:
                            existing = f.read()
                    new_rules = "\n".join(f"- {r}" if not r.strip().startswith("-") else r for r in plan.core_rules_add if r.strip())
                    if new_rules:
                        with open(rules_path, "a", encoding="utf-8") as f:
                            f.write("\n\n" + new_rules)
                        yield {"type": "upgrade_progress", "phase": "core_rules", "detail": f"已追加 {len(plan.core_rules_add)} 条规则"}
                        await self._broadcast_content("✅ 已更新 Agent 进化规则，下次对话生效")
                except Exception as e:
                    logger.warning(f"Failed to append core rules: {e}")
            
            # 2.5 Git checkpoint（升级前保存状态）
            if self.on_git_checkpoint:
                ok, msg = self.on_git_checkpoint()
                yield {"type": "upgrade_progress", "phase": "git_checkpoint", "detail": msg}
                if not ok:
                    logger.warning(f"Git checkpoint: {msg}")
            
            # 3. 执行步骤
            for i, step in enumerate(plan.steps):
                target = step.get("target", "terminal")
                yield {"type": "upgrade_progress", "phase": "executing", "step": i + 1, "target": target}
                
                if target == "terminal" and step.get("command"):
                    cmd = step["command"]
                    # 跳过无效的 pip install（smtplib/email/ssl 等是标准库）
                    skip_modules = ("smtplib", "email", "ssl", "json", "os ", "re ", "asyncio ")
                    if "pip install" in cmd.lower():
                        for m in skip_modules:
                            if m in cmd.lower():
                                logger.info(f"Skipping invalid pip install (stdlib): {cmd[:80]}")
                                result = DispatchResult(success=True, target=DispatchTarget.TERMINAL, output=f"跳过：{m} 是标准库")
                                break
                        else:
                            result = await self.dispatcher.dispatch_to_terminal(cmd, working_dir=MACAGENT_ROOT)
                    else:
                        result = await self.dispatcher.dispatch_to_terminal(cmd, working_dir=MACAGENT_ROOT)
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
                    full_task = self._build_cursor_task(step, plan)
                    # 1) Cursor CLI  2) Cursor GUI  3) LLM 自主生成  4) 仅打开 Cursor
                    result = DispatchResult(success=False, target=DispatchTarget.CURSOR)
                    auto_mode = None
                    # 1. Cursor CLI（内部任务注入）
                    curs_result, cli_used = await self.dispatcher.dispatch_to_cursor_cli(
                        project_path=MACAGENT_ROOT,
                        task_prompt=full_task
                    )
                    if cli_used and curs_result.success:
                        result, auto_mode = curs_result, "cli"
                    if not result.success:
                        # 2. Cursor GUI 键盘模拟
                        gui_result, gui_used = await self.dispatcher.dispatch_to_cursor_gui_auto(
                            project_path=MACAGENT_ROOT,
                            task_prompt=full_task
                        )
                        if gui_used and gui_result.success:
                            result, auto_mode = gui_result, "gui"
                        elif gui_used:
                            result = gui_result
                    if not result.success:
                        # 3. LLM 自主生成（不依赖 Cursor，稳定回退）
                        gen_ok, gen_err, output_path = await self._generate_tool_via_llm(step, plan)
                        if gen_ok and output_path:
                            tool_name = (plan.tool_spec.get("name", "new_tool") or "new_tool").replace("-", "_")
                            try:
                                from agent.upgrade_security import approve_tool as do_approve
                                ok, _ = do_approve(output_path, tool_name)
                                if ok:
                                    logger.info(f"Auto-approved LLM-generated tool: {tool_name}")
                            except Exception as e:
                                logger.warning(f"Auto-approve failed: {e}")
                            result = DispatchResult(success=True, target=DispatchTarget.CURSOR, output="LLM 已生成工具代码")
                            auto_mode = "llm"
                        else:
                            logger.info(f"LLM tool gen: {gen_err}")
                    if not result.success:
                        # 4. 仅打开 Cursor（手动完成）
                        result = await self.dispatcher.dispatch_to_cursor(
                            project_path=MACAGENT_ROOT,
                            task_prompt=full_task
                        )
                    yield {
                        "type": "upgrade_step_result",
                        "target": "cursor",
                        "success": result.success,
                        "output": result.output,
                        "error": result.error
                    }
                    if result.success:
                        if auto_mode == "cli":
                            await self._broadcast_content(
                                "✅ Cursor CLI 已自动执行完成，正在加载新工具..."
                            )
                        elif auto_mode == "gui":
                            await self._broadcast_content(
                                "✅ 已通过键盘模拟将任务发送到 Cursor Composer/Chat。"
                                "若未填入：请在 系统设置→隐私与安全性→辅助功能 中授予运行后端的应用权限。"
                            )
                        elif auto_mode == "llm":
                            await self._broadcast_content(
                                "✅ LLM 已自主生成工具代码并写入 tools/generated/，正在加载..."
                            )
                        else:
                            await self._broadcast_content(
                                "📋 Cursor 已打开，任务已写入 .cursor/prompts/upgrade.md。"
                                "请用 Cmd+I (Composer) 或 Cmd+L (Chat) 让 AI 完成该任务。"
                            )
                    elif not result.success:
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
            # Git 回滚
            if self.on_git_rollback:
                ok, msg = self.on_git_rollback()
                logger.info(f"Git rollback: {msg}")
                await self._broadcast_content(f"已回滚工作区: {msg}")
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
    on_trigger_restart: Optional[Callable[[], Any]] = None,
    on_git_checkpoint: Optional[Callable[[], tuple]] = None,
    on_git_rollback: Optional[Callable[[], tuple]] = None
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
            on_trigger_restart=on_trigger_restart,
            on_git_checkpoint=on_git_checkpoint,
            on_git_rollback=on_git_rollback
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
        if on_git_checkpoint is not None:
            _orchestrator.on_git_checkpoint = on_git_checkpoint
        if on_git_rollback is not None:
            _orchestrator.on_git_rollback = on_git_rollback
    return _orchestrator
