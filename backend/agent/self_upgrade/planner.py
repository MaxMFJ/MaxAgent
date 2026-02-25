"""
Planner (LLM)
Outputs JSON only. Must NOT generate code.
"""

import json
import logging
from typing import Optional

from .models import UpgradePlan
from .workspace import PROJECT_ROOT, TOOLS_GENERATED_DIR

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """你是一个 MacAgent 升级规划师。根据用户目标输出**纯 JSON** 计划，不要生成任何代码。

用户目标：{goal}

输出格式（严格 JSON）：
{{
  "goal": "用户目标简述",
  "plan": "实现方案的文字描述（不包含代码）",
  "target_files": ["tools/generated/xxx_tool.py"],
  "strategy": "EXISTING_TOOLS | LLM_SCRIPT | CURSOR_CLI | CURSOR_GUI",
  "reason": "选择该策略的原因"
}}

规则：
- target_files 必须是 tools/generated/ 下的路径，如 tools/generated/example_tool.py
- 不要写代码，只描述方案
- strategy: 若已有工具可完成用 EXISTING_TOOLS；单文件简单逻辑用 LLM_SCRIPT；多文件/守护进程/监控用 CURSOR_CLI；需要人工交互用 CURSOR_GUI
- 项目根目录：{project_root}
- 工具目录：{tools_dir}

只返回 JSON，无其他文字。"""


async def plan_upgrade(goal: str, llm_chat) -> Optional[UpgradePlan]:
    """
    Call LLM to produce upgrade plan.
    llm_chat: async (messages, tools=None) -> {content: str}
    """
    prompt = PLANNER_PROMPT.format(
        goal=goal,
        project_root=PROJECT_ROOT,
        tools_dir=TOOLS_GENERATED_DIR,
    )
    messages = [
        {"role": "system", "content": "你输出严格的 JSON，不生成代码。"},
        {"role": "user", "content": prompt},
    ]
    try:
        response = await llm_chat(messages, tools=None)
        content = (response.get("content") or "").strip()
        # Extract JSON block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        data = json.loads(content)
        plan = UpgradePlan.from_dict(data)
        # Ensure target_files are under tools/generated/
        normalized = []
        for f in plan.target_files:
            f = f.replace("\\", "/").strip()
            if not f.startswith("tools/generated/"):
                f = "tools/generated/" + f.lstrip("/").split("/")[-1]
            if not f.endswith(".py"):
                base = f.rstrip("_").rstrip("/")
                f = f"{base}_tool.py" if not base.endswith("_tool") else base + ".py"
            normalized.append(f)
        plan.target_files = normalized
        logger.info(f"[Upgrade] Planned: {plan.goal} strategy={plan.strategy.value}")
        return plan
    except json.JSONDecodeError as e:
        logger.error(f"[Upgrade] Planner JSON parse error: {e}")
        return None
    except Exception as e:
        logger.exception(f"[Upgrade] Planner failed: {e}")
        return None
