"""
Prompt Loader - 加载 System Prompt 与进化规则
参考 OpenClaw 的 Bootstrap 模块化设计：从 data/prompts/*.md 加载，便于扩展维护
企业级：Query 分级（query_classifier）驱动分层 Prompt（FULL/LITE）+ intent 注入
"""

import logging
import os
from typing import Optional, List, Tuple

from .query_classifier import Intent, QueryTier, classify

logger = logging.getLogger(__name__)

# Bootstrap 配置（支持 MACAGENT_DATA_DIR 打包路径）
from paths import DATA_DIR as _DATA_DIR

_PROMPTS_DIR = os.path.join(_DATA_DIR, "prompts")
BOOTSTRAP_MAX_CHARS = int(os.environ.get("MACAGENT_BOOTSTRAP_MAX_CHARS", "8000"))
BOOTSTRAP_TOTAL_MAX_CHARS = int(os.environ.get("MACAGENT_BOOTSTRAP_TOTAL_MAX_CHARS", "20000"))

# 加载顺序：identity → behavior → tools → capsule → constraints（evolved 单独追加）
BOOTSTRAP_FILES = [
    ("identity", os.path.join(_PROMPTS_DIR, "identity.md")),
    ("behavior", os.path.join(_PROMPTS_DIR, "behavior.md")),
    ("tools", os.path.join(_PROMPTS_DIR, "tools.md")),
    ("capsule", os.path.join(_PROMPTS_DIR, "capsule.md")),
    ("constraints", os.path.join(_PROMPTS_DIR, "constraints.md")),
]

# 项目上下文（类 CLAUDE.md），供 Agent 每轮注入，减少漂移
MACAGENT_CONTEXT_PATH = os.path.join(_PROMPTS_DIR, "MACAGENT.md")
PROJECT_CONTEXT_MAX_CHARS = int(os.environ.get("MACAGENT_PROJECT_CONTEXT_MAX_CHARS", "2000"))

# ── 内嵌兜底（Bootstrap 文件缺失时使用）────────────────────────────────────────
SYSTEM_PROMPT_LITE_FALLBACK = """你是 Chow Duck，macOS 智能助手。
核心能力：文件操作、终端命令、应用控制、系统信息、剪贴板、截图、鼠标键盘、邮件、技能Capsule。
规则：以用户目标为导向，简洁高效，用中文回复。截图完成后立即停止。
若用户只是追问「项目/文件在哪个目录」「做到哪一步了」等，根据对话历史直接回答，不要重新执行创建或命令。"""

SYSTEM_PROMPT_FULL_FALLBACK = """你是 Chow Duck，macOS 智能助手，可帮用户完成各种电脑操作。

## 核心能力
文件操作 | 终端命令 | 应用控制 | 系统信息 | 剪贴板 | 截图(screenshot+app_name) | 鼠标键盘(input_control)

## 行为准则
- 以用户最终目标为导向，工具执行成功但目标未达成时继续尝试
- **工具失败时**：必须明确告知用户失败原因，禁止谎称成功或完成。自动补救 → 引导用户 → 请求工具升级
- 简洁高效，完成后简短报告。截图完成后立即停止。批量操作优先用终端。危险操作先确认

## 启动长期运行进程（Flask/后端/开发服务器）
- 启动 Flask、Node 开发服务器等**不会自动退出的进程**时，必须使用 terminal 的 `background: true` 参数
- 否则会因超时被判定为失败，即使进程实际已启动

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
    """LITE 版：仅 identity + 追问规则"""
    identity_path = os.path.join(_PROMPTS_DIR, "identity.md")
    behavior_path = os.path.join(_PROMPTS_DIR, "behavior.md")
    identity = _load_bootstrap_section(identity_path, 600)
    behavior = _load_bootstrap_section(behavior_path, 400)
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

    # Intent 注入：纯追问时显式提示模型仅根据历史回答
    intent_hint = ""
    if result.intent == Intent.INFORMATION:
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

    # 匹配的 Capsule 技能注入：LLM 明确知道有哪些技能可用，提高调用率
    capsule_hint = ""
    if result.tier != QueryTier.SIMPLE and query:
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
    return base + intent_hint + created_files_hint + capsule_hint + workspace_hint + terminal_hint + evolved


# 向后兼容
SYSTEM_PROMPT_LITE = SYSTEM_PROMPT_LITE_FALLBACK
SYSTEM_PROMPT_FULL = SYSTEM_PROMPT_FULL_FALLBACK
SYSTEM_PROMPT = SYSTEM_PROMPT_FULL_FALLBACK
