"""
Executors: LLM Script, Cursor CLI, Cursor GUI
Each blocks until result known.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Tuple

from .workspace import PROJECT_ROOT, TOOLS_GENERATED_DIR, write_project_file
from .models import UpgradePlan, UpgradeStage

logger = logging.getLogger(__name__)

# Reuse resource dispatcher
def _get_dispatcher():
    try:
        from agent.resource_dispatcher import get_resource_dispatcher
        return get_resource_dispatcher()
    except ImportError:
        return None


async def execute_llm_script(
    plan: UpgradePlan,
    llm_chat,
    task_update_stage,
) -> Tuple[bool, str]:
    """
    LLM generates code only. No paths from LLM.
    Agent writes via write_project_file.
    Stage: EXECUTING_LLM
    """
    if task_update_stage:
        task_update_stage(UpgradeStage.EXECUTING_LLM)

    target = plan.target_files[0] if plan.target_files else "tools/generated/new_tool.py"
    if not target.startswith("tools/generated/"):
        target = "tools/generated/" + target.split("/")[-1]
    if not target.endswith(".py"):
        target = target.rstrip("_") + "_tool.py"

    prompt = f"""生成 MacAgent 工具 Python 代码。

需求：{plan.plan}

要求：
1. 继承 from tools.base import BaseTool, ToolResult, ToolCategory
2. 实现 name, description, parameters (JSON Schema), async def execute(**kwargs) -> ToolResult
3. 禁止使用 subprocess.run，用 asyncio.create_subprocess_shell/exec
4. 禁止 pip install 标准库（smtplib、email、ssl、json、os 等）
5. 输出完整 Python 代码，不要 markdown 标记外的任何文字
6. 不要包含文件路径或输出路径

只输出 Python 代码："""

    try:
        response = await llm_chat(
            [
                {"role": "system", "content": "你只输出 Python 代码，无其他内容。"},
                {"role": "user", "content": prompt},
            ],
            tools=None,
        )
        content = (response.get("content") or "").strip()
        if "```python" in content:
            content = content.split("```python")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        if not content or "from tools.base" not in content:
            return False, "LLM 未返回有效工具代码"

        # Security check
        try:
            from agent.upgrade_security import check_code_safety, is_path_allowed
        except ImportError:
            check_code_safety = lambda c: (True, "")
            is_path_allowed = lambda p: True

        safe, err = check_code_safety(content)
        if not safe:
            return False, f"安全校验失败: {err}"

        abs_path = os.path.join(PROJECT_ROOT, target)
        if not is_path_allowed(abs_path):
            return False, f"路径不允许: {target}"

        written = write_project_file(target, content)
        if written:
            logger.info("[Upgrade] LLM Script success")
            return True, written
        return False, "写入文件失败"
    except Exception as e:
        logger.exception(f"[Upgrade] LLM Script failed: {e}")
        return False, str(e)


async def execute_cursor_cli(
    plan: UpgradePlan,
    task_update_stage,
) -> Tuple[bool, str]:
    """
    Run: cursor agent -p --force <prompt>
    cwd = PROJECT_ROOT
    Stage: EXECUTING_CURSOR_CLI
    """
    if task_update_stage:
        task_update_stage(UpgradeStage.EXECUTING_CURSOR_CLI)

    dispatcher = _get_dispatcher()
    if not dispatcher:
        return False, "ResourceDispatcher 不可用"

    task_prompt = f"""创建 MacAgent 工具。

目标：{plan.goal}
方案：{plan.plan}

要求：
1. 在 tools/generated/ 创建 Python 工具文件
2. 继承 BaseTool, 实现 name, description, parameters, execute
3. 不要创建在 ~/ 或用户目录

输出到 tools/generated/ 目录。"""

    try:
        result, used = await dispatcher.dispatch_to_cursor_cli(
            project_path=PROJECT_ROOT,
            task_prompt=task_prompt,
        )
        if not used:
            return False, result.error or "Cursor CLI 不可用"

        success = result.success
        if success:
            # Check target file created
            for rel in plan.target_files:
                p = os.path.join(PROJECT_ROOT, rel)
                if os.path.exists(p):
                    logger.info("[Upgrade] Cursor CLI success")
                    return True, p
            logger.info("[Upgrade] Cursor CLI finished, target may be created")
            return True, result.output or "执行完成"
        return False, result.error or "Cursor CLI 执行失败"
    except Exception as e:
        logger.exception(f"[Upgrade] Cursor CLI failed: {e}")
        return False, str(e)


async def execute_cursor_gui(
    plan: UpgradePlan,
    task_update_stage,
    timeout_seconds: int = 300,
) -> Tuple[bool, str]:
    """
    Open Cursor workspace, wait for target files changed or timeout.
    Stage: EXECUTING_CURSOR_GUI
    """
    if task_update_stage:
        task_update_stage(UpgradeStage.EXECUTING_CURSOR_GUI)

    dispatcher = _get_dispatcher()
    if not dispatcher:
        return False, "ResourceDispatcher 不可用"

    task_prompt = f"""创建 MacAgent 工具。

目标：{plan.goal}
方案：{plan.plan}

在 tools/generated/ 创建工具文件。"""

    try:
        # Record mtimes before
        mtimes_before = {}
        for rel in plan.target_files:
            p = os.path.join(PROJECT_ROOT, rel)
            if os.path.exists(p):
                mtimes_before[p] = os.path.getmtime(p)

        result, used = await dispatcher.dispatch_to_cursor_gui_auto(
            project_path=PROJECT_ROOT,
            task_prompt=task_prompt,
        )
        if not used:
            return False, result.error or "Cursor GUI 不可用"

        if not result.success:
            return False, result.error or "Cursor GUI 打开失败"

        # Wait for target file created/changed
        start = time.time()
        check_interval = 3.0
        while time.time() - start < timeout_seconds:
            await asyncio.sleep(check_interval)
            for rel in plan.target_files:
                p = os.path.join(PROJECT_ROOT, rel)
                if os.path.exists(p):
                    mtime = os.path.getmtime(p)
                    if p not in mtimes_before or mtime > mtimes_before[p]:
                        logger.info("[Upgrade] Cursor GUI success (file changed)")
                        return True, p
            # Also accept any new file in tools/generated/
            if os.path.isdir(TOOLS_GENERATED_DIR):
                for f in os.listdir(TOOLS_GENERATED_DIR):
                    if f.endswith(".py") and f not in [os.path.basename(r) for r in plan.target_files]:
                        p = os.path.join(TOOLS_GENERATED_DIR, f)
                        if p not in mtimes_before:
                            mtimes_before[p] = 0
                        if os.path.getmtime(p) > mtimes_before.get(p, 0):
                            logger.info("[Upgrade] Cursor GUI success (new file)")
                            return True, p

        logger.warning("[Upgrade] Cursor GUI timeout")
        return False, f"超时 ({timeout_seconds}s)，目标文件未检测到变化"
    except Exception as e:
        logger.exception(f"[Upgrade] Cursor GUI failed: {e}")
        return False, str(e)
