"""
Prompt Loader - 加载 System Prompt 与进化规则
参考 OpenClaw 的 Bootstrap 模块化设计：从 data/prompts/*.md 加载，便于扩展维护
企业级：Query 分级（query_classifier）驱动分层 Prompt（FULL/LITE）+ intent 注入
"""

import logging
import os
import time as _time_mod
from datetime import datetime
from typing import Optional, List, Tuple

from .query_classifier import Intent, QueryTier, classify

logger = logging.getLogger(__name__)

# Bootstrap 配置（支持 MACAGENT_DATA_DIR 打包路径）
from paths import DATA_DIR as _DATA_DIR

_PROMPTS_DIR = os.path.join(_DATA_DIR, "prompts")
BOOTSTRAP_MAX_CHARS = int(os.environ.get("MACAGENT_BOOTSTRAP_MAX_CHARS", "8000"))
BOOTSTRAP_TOTAL_MAX_CHARS = int(os.environ.get("MACAGENT_BOOTSTRAP_TOTAL_MAX_CHARS", "20000"))

# 加载顺序：identity → behavior → tools → capsule → runbook → constraints（evolved 单独追加）
BOOTSTRAP_FILES = [
    ("identity", os.path.join(_PROMPTS_DIR, "identity.md")),
    ("behavior", os.path.join(_PROMPTS_DIR, "behavior.md")),
    ("tools", os.path.join(_PROMPTS_DIR, "tools.md")),
    ("capsule", os.path.join(_PROMPTS_DIR, "capsule.md")),
    ("runbook", os.path.join(_PROMPTS_DIR, "runbook.md")),
    ("constraints", os.path.join(_PROMPTS_DIR, "constraints.md")),
]

# 项目上下文（类 CLAUDE.md），供 Agent 每轮注入，减少漂移
MACAGENT_CONTEXT_PATH = os.path.join(_PROMPTS_DIR, "MACAGENT.md")
PROJECT_CONTEXT_MAX_CHARS = int(os.environ.get("MACAGENT_PROJECT_CONTEXT_MAX_CHARS", "2000"))

# ── 内嵌兜底（Bootstrap 文件缺失时使用）────────────────────────────────────────
SYSTEM_PROMPT_LITE_FALLBACK = """你是 Chow Duck，运行在 macOS 上的全能智能助手。你既是系统级操作执行者，也是多领域知识顾问（产品、开发、法律、生活、购物、出行、旅游、学习等）。
核心能力：文件操作、终端命令、应用控制、系统信息、剪贴板、截图、鼠标键盘(input_control)、邮件、技能Capsule、知识咨询。
规则：知识/咨询类问题直接回答无需工具；操作类任务用工具执行。以用户目标为导向，简洁高效，用中文回复。截图完成后立即停止。
GUI 操作：键盘输入中文必须用 input_control 的 keyboard_type（严禁 osascript keystroke 输入中文）。每步操作后截图验证，finish 前截图确认任务完成。
若用户只是追问「项目/文件在哪个目录」「做到哪一步了」等，根据对话历史直接回答，不要重新执行创建或命令。"""

SYSTEM_PROMPT_FULL_FALLBACK = """你是 Chow Duck，运行在 macOS 上的全能智能助手。你不仅能执行电脑操作，更是用户日常工作与生活中的全域知识顾问。

## 核心能力
### 系统操作
文件操作 | 终端命令 | 应用控制 | 系统信息 | 剪贴板 | 截图(screenshot+app_name) | 鼠标键盘(input_control) | 邮件(SMTP)
### 知识咨询（直接回答，无需工具）
产品设计 | 软件开发 | 法律常识 | 生活服务 | 购物消费 | 出行旅游 | 学习教育 | 财务理财 | 职场效率
### Duck 分身委派
- **duck_status**：查询在线分身列表。**仅委派前调用一次**，委派后禁止轮询
- **delegate_duck**：委派任务给分身（制作 HTML、写代码、设计网页、爬虫等）。description 必填，路径用 ~/Desktop/
- **串行依赖任务（设计→开发）**：第1步 delegate_duck(wait=true) 拿到文件路径，第2步把完整路径写入下一个 delegate_duck 的 description
- **委派后禁止轮询**：调用 delegate_duck 后直接告知用户等待，不要反复调用 duck_status 或 ls 检查进度。系统自动推送完成通知
- **Duck 失败后**：直接用 write_file/terminal 自行完成，禁止再次 delegate_duck 相同内容
### 扩展能力
技能 Capsule（社区库数千个按需加载）| MCP Server（外部协议）| 工具自升级(request_tool_upgrade)

## 行为准则
- **先判断再行动**：知识/咨询类 → 直接回答；操作/执行类 → 用工具；混合类 → 先生成内容再执行
- 以用户最终目标为导向，工具执行成功但目标未达成时继续尝试
- **工具失败时**：必须明确告知用户失败原因，禁止谎称成功或完成。自动补救 → 引导用户 → 请求工具升级
- 简洁高效，完成后简短报告。截图完成后立即停止。批量操作优先用终端。危险操作先确认

## GUI 操作规范（操作微信、Safari 等应用的界面）
### 工具选择（强制）
- **键盘输入文字**（尤其中文）：必须使用 input_control 的 keyboard_type。**严禁**用 terminal 运行 osascript 的 `keystroke "中文"` — keystroke 只支持 ASCII，中文会变成乱码
- **鼠标点击**：使用 input_control 的 mouse_click（传 x, y 坐标）
- **快捷键**：使用 input_control 的 keyboard_shortcut（如 Cmd+F 搜索）
- **单个按键**（回车/Tab/Esc）：使用 input_control 的 keyboard_key
- 仅在无替代方案时才用 terminal 执行 osascript

### GUI 操作流程（必须遵循）
1. 每步操作后必须截图（screenshot），根据截图判断当前状态再决定下一步
2. 不要在一个 osascript 里塞多步操作（搜索+输入+回车），拆成单步并逐步验证
3. 点击/输入前先截图确认目标位置，根据截图的 UI 元素坐标点击
4. finish 前必须截图确认任务真正完成，不要凭假设宣布完成

### 微信/聊天应用典型流程
open_app → 截图 → keyboard_shortcut(Cmd+F) → 截图确认搜索框 → keyboard_type("联系人名") → 截图 → keyboard_key(return)选中结果 → 截图确认进入对话 → mouse_click(点击输入框) → keyboard_type("消息内容") → keyboard_key(return)发送 → 截图验证消息已发送 → finish

### 常见应用快捷键坑（必须遵守）
- **微信发送消息**：用 `keyboard_key(key="return")`。
  • 绝对禁止用 keyboard_shortcut 发送消息！keyboard_shortcut 会附加 command 修饰键，Cmd+Return 在微信中不是发送
  • 也禁止 shift+return（那是换行）
  • 只有纯 Return 才是发送，不需要任何修饰键
- **搜索确认**：keyboard_key(key="return")
- **关闭搜索/对话框**：keyboard_key(key="escape")
- **重要区分**：keyboard_key = 纯按键（无修饰键）；keyboard_shortcut = 带修饰键的快捷键。发送消息必须用 keyboard_key

## 启动长期运行进程（Flask/后端/开发服务器）
- 启动 Flask、Node 开发服务器等**不会自动退出的进程**时，必须使用 terminal 的 `background: true` 参数
- 否则会因超时被判定为失败，即使进程实际已启动

## 邮件(mail工具，SMTP直发，不依赖Mail程序)
- 直接调用 mail 工具。失败时：「未配置」→引导去设置；「连接失败」→说明网络问题，建议重试
- 禁止索要密码，禁止用 input_control 打开 Mail.app

## 工具升级(request_tool_upgrade)
- 用户需要新增Agent工具/能力时，**必须调用** request_tool_upgrade，等待完成后调用新工具
- 生成的工具文件**只能**写入 tools/generated/ 目录
- 禁止用 file_operations 在 ~/ 或 ~/Desktop/ 创建替代 Agent 工具的脚本
- 仅当用户明确要「一次性脚本」且不要求作为Agent工具时，才用 file_operations（输出到 ~/Desktop/）

## 文件输出路径规则
- 用户文档（方案、报告、笔记等）→ 默认保存到 ~/Desktop/
- Agent 工具/技能扩展 → 只能写入 tools/generated/
- 代码项目 → ~/Desktop/项目名/ 或用户指定路径
- 禁止将用户文档写到 ~/（主目录根目录）

## 避免无效循环
- 文件已存在 → 先 read 判断是否满足需求，满足则直接告知
- 目标已达成 → 立即结束，不做冗余改进

## 追问信息（重要）
- 当用户**仅追问之前任务的结果**（如「项目/文件在哪个目录」「项目目录在哪里」「做到哪一步了」「生成了吗」「我去看一下」）时，**根据对话历史直接回答**，不要重新执行创建、写入或运行命令。只有用户明确要求「创建」「生成」「执行」时才动手操作。

## 技能Capsule
- 系统推荐匹配 Capsule 时，直接调用 capsule 工具执行
- 指令型技能(instruction_mode=true)：按指令用已有工具逐步完成

用中文回复，简洁不啰嗦。"""


def _load_bootstrap_section(path: str, max_chars: int) -> str:
    """加载单个 bootstrap 文件，超长则截断"""
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return ""
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n...[已截断]"
        return content
    except Exception as e:
        logger.warning(f"Failed to load bootstrap {path}: {e}")
        return ""


def get_project_context_for_prompt(max_chars: int = None) -> str:
    """加载项目上下文（MACAGENT.md），供 system prompt 注入，截断到 max_chars。"""
    if max_chars is None:
        max_chars = PROJECT_CONTEXT_MAX_CHARS
    content = _load_bootstrap_section(MACAGENT_CONTEXT_PATH, max_chars)
    if not content:
        return ""
    return content.strip()


def _load_bootstrap_full() -> str:
    """加载全部 bootstrap 文件并合并，带总长度限制"""
    parts: List[str] = []
    total = 0
    for name, path in BOOTSTRAP_FILES:
        content = _load_bootstrap_section(path, BOOTSTRAP_MAX_CHARS)
        if not content:
            continue
        remaining = BOOTSTRAP_TOTAL_MAX_CHARS - total
        if remaining <= 0:
            logger.debug(f"Bootstrap total cap reached, skipping {name}")
            break
        if len(content) > remaining:
            content = content[:remaining] + "\n\n...[已截断]"
        parts.append(content)
        total += len(content)
    if not parts:
        return ""
    return "\n\n---\n\n".join(parts)


def _get_full_prompt_from_bootstrap() -> Optional[str]:
    """从 Bootstrap 构建 FULL 版 prompt，失败返回 None"""
    content = _load_bootstrap_full()
    if not content:
        return None
    return content.strip()


def _get_lite_prompt_from_bootstrap() -> Optional[str]:
    """LITE 版：identity（含能力矩阵）+ 追问规则"""
    identity_path = os.path.join(_PROMPTS_DIR, "identity.md")
    behavior_path = os.path.join(_PROMPTS_DIR, "behavior.md")
    identity = _load_bootstrap_section(identity_path, 2000)
    behavior = _load_bootstrap_section(behavior_path, 600)
    if not identity and not behavior:
        return None
    query_hint = "若用户只是追问「项目/文件在哪个目录」「做到哪一步了」等，根据对话历史直接回答，不要重新执行创建或命令。"
    combined = identity
    if query_hint:
        combined = f"{combined}\n\n{query_hint}" if combined else query_hint
    return combined.strip() if combined else None


# 缓存：避免每次请求都读文件
_bootstrap_full_cache: Optional[Tuple[float, str]] = None
_bootstrap_lite_cache: Optional[Tuple[float, str]] = None
_CACHE_TTL = 60.0  # 秒


def _get_cached_bootstrap_full() -> str:
    """带缓存的 FULL bootstrap"""
    global _bootstrap_full_cache
    import time
    now = time.time()
    if _bootstrap_full_cache and (now - _bootstrap_full_cache[0]) < _CACHE_TTL:
        return _bootstrap_full_cache[1]
    content = _get_full_prompt_from_bootstrap()
    if content:
        _bootstrap_full_cache = (now, content)
        return content
    return SYSTEM_PROMPT_FULL_FALLBACK


def _get_cached_bootstrap_lite() -> str:
    """带缓存的 LITE bootstrap"""
    global _bootstrap_lite_cache
    import time
    now = time.time()
    if _bootstrap_lite_cache and (now - _bootstrap_lite_cache[0]) < _CACHE_TTL:
        return _bootstrap_lite_cache[1]
    content = _get_lite_prompt_from_bootstrap()
    if content:
        _bootstrap_lite_cache = (now, content)
        return content
    return SYSTEM_PROMPT_LITE_FALLBACK


def _load_evolved_rules() -> str:
    """加载自升级追加的 Agent 规则（data/agent_evolved_rules.md）"""
    try:
        rules_path = os.path.join(_DATA_DIR, "agent_evolved_rules.md")
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
    """兼容旧接口：返回 'simple' 或 'complex'，由 query_classifier 驱动"""
    result = classify(query)
    return result.tier.value


def get_full_system_prompt() -> str:
    """获取完整 System Prompt（FULL 版 + 进化规则），向后兼容"""
    base = _get_cached_bootstrap_full()
    evolved = _load_evolved_rules()
    return base + evolved


# 时间相关关键词：检测到时自动注入当前系统时间
_TIME_KEYWORDS = (
    '当前', '现在', '目前', '此刻', '今天', '今日', '明天', '昨天', '后天', '前天',
    '今年', '去年', '明年', '本月', '上月', '下月', '本周', '上周', '下周',
    '最新', '最近', '这几天', '近期', '眼下',
    '几点', '什么时候', '多久', '时间', '日期', '星期',
    '早上', '上午', '中午', '下午', '晚上', '凌晨', '今早', '今晚',
    'today', 'now', 'current', 'latest', 'this week', 'this month', 'this year',
    'yesterday', 'tomorrow', 'recent',
)

_WEEKDAY_NAMES = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def _needs_time_injection(query: str) -> bool:
    """检测用户查询是否涉及时间相关概念"""
    q = query.lower()
    return any(kw in q for kw in _TIME_KEYWORDS)


def _build_time_hint() -> str:
    """构建当前系统时间提示"""
    now = datetime.now()
    weekday = _WEEKDAY_NAMES[now.weekday()]
    time_str = now.strftime(f"%Y-%m-%d %H:%M:%S ({weekday})")
    tz_name = _time_mod.strftime("%Z") or "Local"
    return f"\n\n[系统时间：{time_str}，时区：{tz_name}。请基于此精确时间回答用户关于时间的问题。]"


def get_system_prompt_for_query(query: str, session_id: Optional[str] = None) -> str:
    """企业级分层 Prompt：由 query_classifier 分级，并注入 intent 提示"""
    from .context_manager import context_manager

    result = classify(query, session_id=session_id)
    base = _get_cached_bootstrap_lite() if result.tier == QueryTier.SIMPLE else _get_cached_bootstrap_full()
    # 注入项目上下文（MACAGENT.md），减少长对话漂移
    project_ctx = get_project_context_for_prompt()
    if project_ctx:
        base = project_ctx + "\n\n---\n\n" + base
    logger.info("prompt_tier=%s intent=%s query_preview=%s", result.tier.value, result.intent.value, result.query_preview[:30])

    # Intent 注入：根据分类结果指导模型行为
    intent_hint = ""
    if result.intent == Intent.INFORMATION:
        if result.tier == QueryTier.COMPLEX:
            # 知识咨询型：COMPLEX tier + INFORMATION intent（如分析、方案、攻略等）
            intent_hint = "\n\n[当前判定：知识咨询类问题，请充分运用你的多领域知识直接给出高质量回答。如无必要不调用工具，除非用户明确要求保存/执行。]"
        else:
            # 纯追问型：SIMPLE tier + INFORMATION intent（如"文件在哪"）
            intent_hint = "\n\n[当前判定：用户为信息追问，请仅根据对话历史回答，不要执行创建/写入/运行等操作。]"
    elif result.intent == Intent.GREETING:
        intent_hint = "\n\n[当前判定：简单问候，简洁回复即可。]"

    # 本会话已创建文件注入：LLM 能回答「项目/文件在哪里」等追问
    created_files_hint = ""
    if session_id:
        try:
            ctx = context_manager.get_or_create(session_id)
            if ctx.created_files:
                lines = "\n".join(f"- {p}" for p in ctx.created_files)
                created_files_hint = f"\n\n[本会话中你已创建/写入的文件（用户追问位置时请直接引用）：\n{lines}\n]"
        except Exception as e:
            logger.debug(f"Failed to inject created_files hint: {e}")

    # 匹配的 Capsule 技能注入：仅对需要执行的请求注入，知识咨询跳过以减少延迟
    capsule_hint = ""
    if result.tier != QueryTier.SIMPLE and result.intent == Intent.EXECUTION and query:
        try:
            from .capsule_registry import get_capsule_registry
            reg = get_capsule_registry()
            caps = reg.find_capsule_by_task(query, limit=3, min_score=0.6)
            if caps:
                def _cap_line(c):
                    d = (c.description or "")[:80]
                    if len(c.description or "") > 80:
                        d += "..."
                    return f"- {c.id}: {d}" if d else f"- {c.id}"
                lines = "\n".join(_cap_line(c) for c in caps)
                capsule_hint = f"\n\n[推荐技能（优先调用 capsule 执行）：\n{lines}\n]"
        except Exception as e:
            logger.debug(f"Failed to inject capsule hint: {e}")

    # 在线技能索引注入（COMPLEX 时）：让 LLM 快速了解可加载的 OpenClaw 技能，用 capsule find 按需匹配
    if result.tier == QueryTier.COMPLEX:
        try:
            from .skill_index import get_skill_index_for_prompt
            index_hint = get_skill_index_for_prompt(max_chars=1200)
            if index_hint:
                if capsule_hint:
                    capsule_hint += f"\n\n[{index_hint}]"
                else:
                    capsule_hint = f"\n\n[{index_hint}]"
        except Exception as e:
            logger.debug(f"Failed to inject skill index: {e}")

    # Workspace 上下文注入（当前工作区、打开的文件）
    workspace_hint = ""
    try:
        from .workspace_context import get_workspace_context
        wctx = get_workspace_context()
        ws_info = wctx.get_prompt_hint(session_id)
        if ws_info:
            workspace_hint = f"\n\n{ws_info}"
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Failed to inject workspace hint: {e}")

    # 终端会话上下文注入（上条命令的 cwd、输出，供后续命令参考）
    terminal_hint = ""
    if session_id:
        try:
            from .terminal_session import get_terminal_session_store
            terminal_hint = get_terminal_session_store().get_context_hint(session_id)
            if terminal_hint:
                terminal_hint = f"\n\n{terminal_hint}"
        except Exception as e:
            logger.debug(f"Failed to inject terminal hint: {e}")

    evolved = _load_evolved_rules()

    # 时间感知注入：检测到时间相关查询时，注入当前系统时间
    time_hint = _build_time_hint() if _needs_time_injection(query) else ""

    # RPA Runbook 提示注入：仅对执行类请求注入，且仅当匹配分数达到阈值时注入，减少无关流程干扰
    runbook_hint = ""
    if result.tier != QueryTier.SIMPLE and result.intent == Intent.EXECUTION and query:
        try:
            from .runbook_registry import get_runbook_registry
            rb_reg = get_runbook_registry()
            inject_min = float(os.environ.get("MACAGENT_RUNBOOK_INJECT_MIN_SCORE", "0.45"))
            inject_categories_raw = os.environ.get("MACAGENT_RUNBOOK_INJECT_CATEGORIES", "")
            inject_categories = [c.strip() for c in inject_categories_raw.split(",") if c.strip()] or None
            scored_list = rb_reg.find_by_query_with_scores(
                query, limit=5, min_score=0.35, categories=inject_categories
            )
            above_threshold = [(rb, s) for rb, s in scored_list if s >= inject_min][:3]
            if above_threshold:
                runbooks = [rb for rb, _ in above_threshold]
                lines = "\n".join(
                    f"- {rb.id} [{rb.category}]: {rb.description[:80]}"
                    + ("（可委派 Duck）" if getattr(rb, "prefer_duck", False) else "")
                    for rb in runbooks
                )
                runbook_hint = (
                    f"\n\n[可用 RPA 自动化流程（Runbook）：以下标准化流程与当前请求匹配，"
                    f"优先推荐用户直接执行；调用方式：告知用户或直接按步骤执行。\n{lines}\n]"
                )
        except Exception as e:
            logger.debug(f"Failed to inject runbook hint: {e}")

    return base + time_hint + intent_hint + created_files_hint + capsule_hint + workspace_hint + terminal_hint + runbook_hint + evolved


# 向后兼容
SYSTEM_PROMPT_LITE = SYSTEM_PROMPT_LITE_FALLBACK
SYSTEM_PROMPT_FULL = SYSTEM_PROMPT_FULL_FALLBACK
SYSTEM_PROMPT = SYSTEM_PROMPT_FULL_FALLBACK
