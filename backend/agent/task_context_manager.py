"""
Task Context Manager - 任务级上下文隔离
解决 Agent 在不同任务间复用目标应用导致的上下文污染问题

Pipeline:
  User Input → Intent Detection → Task Context Manager → Tool Selection → Param Extraction → Execute
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    ACTIVE = "active"
    DONE = "done"


@dataclass
class TaskContext:
    """
    单次用户任务的上下文
    与 action_schema.TaskContext 不同：本类用于 Chat 模式下的目标应用隔离
    """
    task_type: str  # screenshot, email, open_app, etc.
    target: Optional[str] = None  # Mail.app, Safari, Finder, etc. (canonical app name)
    created_at: datetime = field(default_factory=datetime.now)
    actions: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.ACTIVE

    def mark_done(self) -> None:
        """标记任务完成"""
        self.status = TaskStatus.DONE


# 用户输入中的别名 -> macOS 应用名
# 支持中英文、常见简称
APP_ALIASES: Dict[str, str] = {
    # Email
    "email": "Mail",
    "邮件": "Mail",
    "mail": "Mail",
    "mail.app": "Mail",
    # Browser
    "browser": "Safari",
    "浏览器": "Safari",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "chromium": "Google Chrome",
    "firefox": "Firefox",
    "edge": "Microsoft Edge",
    # Finder
    "finder": "Finder",
    "访达": "Finder",
    "桌面": "Finder",
    # Terminal
    "terminal": "Terminal",
    "终端": "Terminal",
    "iterm": "iTerm",
    "iterm2": "iTerm",
    # Common
    "wechat": "WeChat",
    "微信": "WeChat",
    "slack": "Slack",
    "notes": "Notes",
    "备忘录": "Notes",
    "calendar": "Calendar",
    "日历": "Calendar",
}

# 需要绑定 target (app_name) 的工具
TOOLS_NEEDING_TARGET: List[str] = [
    "screenshot",
    "vision",  # vision_tool 也接受 app_name
    "app_control",  # open/close/activate 等
    "gui_automation",  # dynamic_tool_generator 中的 GUI 工具
]

# 单步任务：执行一次即完成，应清除 current_task
SINGLE_STEP_TASK_TYPES: List[str] = ["screenshot", "open_app"]


def extract_explicit_target(user_message: str) -> Optional[str]:
    """
    从用户输入中提取显式指定的目标应用
    当用户说 "screenshot browser"、"screenshot chrome" 等时，必须覆盖上一任务的目标

    Returns:
        规范化的应用名称（如 "Safari", "Mail"），未检测到则返回 None
    """
    if not user_message or not isinstance(user_message, str):
        return None
    msg = user_message.strip().lower()
    if len(msg) < 2:
        return None

    # 模式：screenshot/截图 + 目标
    patterns = [
        r"(?:screenshot|截图)\s+(?:of\s+)?(?:the\s+)?(\w+)",
        r"(?:screenshot|截图)\s+(\w+)",
        r"截(\w+)的图",
        r"(?:open|打开)\s+(\w+)",
        r"(?:close|关闭)\s+(\w+)",
        r"(?:activate|激活|切换)\s+(?:to\s+)?(\w+)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            word = m.group(1).strip()
            if not word:
                continue
            # 查别名映射
            canonical = APP_ALIASES.get(word.lower())
            if canonical:
                return canonical
            # 未在别名中：首字母大写的应用名（如 Safari, Chrome）
            if word.lower() in ("the", "a", "an"):
                continue
            return word[0].upper() + word[1:].lower()

    # 中文模式：截图 浏览器 / 截图 邮件 / 截图邮件
    for alias, app in APP_ALIASES.items():
        if alias not in msg:
            continue
        if "截图" in msg or "screenshot" in msg:
            if re.search(rf"(?:截图|screenshot)\s*{re.escape(alias)}", msg, re.I):
                return app
            if re.search(rf"(?:截图|screenshot).*{re.escape(alias)}", msg, re.I):
                return app
        if "打开" in msg or "open" in msg:
            if re.search(rf"(?:打开|open)\s*{re.escape(alias)}", msg, re.I):
                return app
            if re.search(rf"(?:打开|open).*{re.escape(alias)}", msg, re.I):
                return app

    return None


def infer_task_type_from_tool(tool_name: str) -> Optional[str]:
    """根据工具名推断任务类型"""
    mapping = {
        "screenshot": "screenshot",
        "vision": "screenshot",
        "app_control": "open_app",
    }
    return mapping.get(tool_name)


def _infer_task_type_from_message(user_message: str) -> str:
    """从用户消息推断任务类型"""
    msg = (user_message or "").lower()
    if "open" in msg or "打开" in msg or "close" in msg or "关闭" in msg:
        return "open_app"
    if "screenshot" in msg or "截图" in msg:
        return "screenshot"
    return "screenshot"  # 默认


def resolve_task(
    user_message: str,
    explicit_target: Optional[str],
    current_task: Optional[TaskContext],
) -> TaskContext:
    """
    解析当前任务上下文

    规则:
    - 无 current_task → 创建新任务
    - 用户输入包含显式目标 → 覆盖，创建新任务
    - 目标与当前任务不同 → 创建新任务
    - 目标相同 → 复用当前任务
    - 当前任务已完成 → 创建新任务

    Returns:
        解析后的 TaskContext（可能是新建或复用）
    """
    # 任务已完成 → 必须新建
    if current_task and current_task.status == TaskStatus.DONE:
        current_task = None

    # 显式目标优先：覆盖上一任务，创建新任务
    if explicit_target:
        task_type = _infer_task_type_from_message(user_message)
        return TaskContext(
            task_type=task_type,
            target=explicit_target,
            created_at=datetime.now(),
            actions=[],
            status=TaskStatus.ACTIVE,
        )

    # 无当前任务 → 新建（target 可能为 None，由 LLM 推断）
    if not current_task:
        task_type = _infer_task_type_from_message(user_message)
        return TaskContext(
            task_type=task_type,
            target=None,
            created_at=datetime.now(),
            actions=[],
            status=TaskStatus.ACTIVE,
        )

    # 复用当前任务
    return current_task


def bind_target_to_tool_args(
    tool_name: str,
    tool_args: Dict[str, Any],
    current_task: Optional[TaskContext],
) -> Dict[str, Any]:
    """
    将 current_task.target 绑定到需要 target 的工具参数中
    工具必须使用 current_task.target，而非全局上下文（防止污染）

    规则:
    - current_task.target 存在时 → 始终使用，覆盖 LLM 可能从历史上下文推断的错误值
    - current_task.target 不存在且 app_name 缺失 → 保持原样（由 LLM 推断）
    """
    if tool_name not in TOOLS_NEEDING_TARGET:
        return tool_args
    if not current_task or not current_task.target:
        return tool_args
    args = dict(tool_args)
    args["app_name"] = current_task.target
    logger.info(f"TaskContext: bound target {current_task.target} to {tool_name}")
    return args


def is_single_step_task(task_type: str, tool_name: str) -> bool:
    """判断是否为单步任务（执行后应清除 current_task）"""
    if task_type in SINGLE_STEP_TASK_TYPES:
        return True
    if tool_name in ("screenshot",) and task_type == "screenshot":
        return True
    return False
