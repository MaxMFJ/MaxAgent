"""
Prompt Loader - 加载 System Prompt 与进化规则
从 Core 抽离，Core 不再直接读写文件
支持分级 Prompt：简单查询用 LITE 版，复杂任务用 FULL 版
"""

import logging
import os

logger = logging.getLogger(__name__)

# ── LITE 版：用于简单对话/查询，大幅精简以节省 token (~400 字符) ──
SYSTEM_PROMPT_LITE = """你是 MacAgent，macOS 智能助手。
核心能力：文件操作、终端命令、应用控制、系统信息、剪贴板、截图、鼠标键盘、邮件、技能Capsule。
规则：以用户目标为导向，简洁高效，用中文回复。截图完成后立即停止。"""

# ── FULL 版：用于需要工具调用的复杂任务 ──
SYSTEM_PROMPT_FULL = """你是 MacAgent，macOS 智能助手，可帮用户完成各种电脑操作。

## 核心能力
文件操作 | 终端命令 | 应用控制 | 系统信息 | 剪贴板 | 截图(screenshot+app_name) | 鼠标键盘(input_control)

## 行为准则
- 以用户最终目标为导向，工具执行成功但目标未达成时继续尝试
- 工具失败时：自动补救 → 引导用户 → 请求工具升级
- 简洁高效，完成后简短报告。截图完成后立即停止。批量操作优先用终端。危险操作先确认

## 邮件(mail工具，SMTP直发，不依赖Mail程序)
- 直接调用 mail 工具。失败时：「未配置」→引导去设置；「连接失败」→说明网络问题，建议重试
- 禁止索要密码，禁止用 input_control 打开 Mail.app

## 工具升级(request_tool_upgrade)
- 用户需要新增Agent工具/能力时，**必须调用** request_tool_upgrade，等待完成后调用新工具
- 工具只在 tools/generated/ 创建，禁止用 file_operations 在 ~/ 写脚本替代
- 仅当用户明确要「一次性脚本」且不要求作为Agent工具时，才用 file_operations

## 避免无效循环
- 文件已存在 → 先 read 判断是否满足需求，满足则直接告知
- 目标已达成 → 立即结束，不做冗余改进

## 技能Capsule
- 系统推荐匹配 Capsule 时，直接调用 capsule 工具执行
- 指令型技能(instruction_mode=true)：按指令用已有工具逐步完成

用中文回复，简洁不啰嗦。"""

# 向后兼容：SYSTEM_PROMPT 指向 FULL 版
SYSTEM_PROMPT = SYSTEM_PROMPT_FULL


def _load_evolved_rules() -> str:
    """加载自升级追加的 Agent 规则（data/agent_evolved_rules.md）"""
    try:
        rules_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "agent_evolved_rules.md"
        )
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            lines = [
                l.strip()
                for l in content.split("\n")
                if l.strip() and not l.strip().startswith("#")
            ]
            if lines:
                return "\n\n## 进化规则\n" + "\n".join(lines)
    except Exception as e:
        logger.warning(f"Failed to load evolved rules: {e}")
    return ""


def _classify_query_complexity(query: str) -> str:
    """
    判断用户查询复杂度：'simple' 或 'complex'
    simple: 闲聊、知识问答、简单问候等不需要工具调用的场景
    complex: 需要操作系统、调用工具、多步骤任务
    """
    q = query.strip().lower()

    # 短问候/闲聊
    if len(q) < 15:
        greetings = ["你好", "hi", "hello", "hey", "嗨", "在吗", "你是谁", "谢谢", "感谢", "好的", "ok"]
        if any(q.startswith(g) or q == g for g in greetings):
            return "simple"

    # 操作性关键词 → complex
    action_keywords = [
        "打开", "关闭", "启动", "运行", "创建", "删除", "移动", "复制", "写入", "读取",
        "执行", "命令", "终端", "截图", "截屏", "发送", "邮件", "搜索", "下载", "安装",
        "监控", "升级", "部署", "编译", "构建", "docker", "git", "brew", "npm", "pip",
        "鼠标", "键盘", "点击", "输入", "粘贴", "剪贴板", "capsule", "技能",
    ]
    if any(kw in q for kw in action_keywords):
        return "complex"

    # 问号结尾的纯知识问答
    if q.endswith("?") or q.endswith("？"):
        if not any(kw in q for kw in ["怎么", "如何", "帮我"]):
            return "simple"

    return "complex"


def get_full_system_prompt() -> str:
    """获取完整 System Prompt（FULL 版 + 进化规则），向后兼容"""
    return SYSTEM_PROMPT_FULL + _load_evolved_rules()


def get_system_prompt_for_query(query: str) -> str:
    """根据查询复杂度选择合适的 System Prompt"""
    complexity = _classify_query_complexity(query)
    if complexity == "simple":
        logger.info(f"Using LITE system prompt for simple query: {query[:30]}...")
        return SYSTEM_PROMPT_LITE + _load_evolved_rules()
    logger.info(f"Using FULL system prompt for complex query: {query[:30]}...")
    return SYSTEM_PROMPT_FULL + _load_evolved_rules()
