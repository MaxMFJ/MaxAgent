"""
Executors: LLM Script
Generates tool code via user's LLM.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Tuple

from .workspace import PROJECT_ROOT, TOOLS_GENERATED_DIR, write_project_file
from .models import UpgradePlan, UpgradeStage

logger = logging.getLogger(__name__)


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

    prompt = f"""生成 Chow Duck 工具 Python 代码。

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
        from ..llm_utils import extract_text_from_content
        content = extract_text_from_content(response.get("content")).strip()
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
