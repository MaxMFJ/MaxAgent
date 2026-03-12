"""
ErrorRecovery — 统一错误恢复基础设施

Chat 模式 (core.py) 与 Autonomous 模式 (autonomous_agent.py) 共享:
- 截断 (truncation) 检测与处理策略
- 解析失败 (parse error) 重试策略
- 截断续传 (tool call 参数不完整时重新生成)
- write_file / create_and_run_script 降级建议
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 首步纯文本阈值 ──
FIRST_STEP_PLAIN_TEXT_MIN_LEN = 200


class ErrorRecovery:
    """
    统一的错误恢复引擎。

    提供截断处理、解析失败重试、降级建议等共享逻辑。
    """

    # ────────────────────── 截断续传 ──────────────────────

    @staticmethod
    def build_truncation_retry_messages(
        tool_names: str,
        current_content: str,
        retry_count: int,
        max_retries: int,
    ) -> tuple:
        """
        构建截断续传的消息对（assistant + user）。

        Returns:
            (assistant_msg, user_msg, warning_text)
        """
        assistant_msg = {
            "role": "assistant",
            "content": current_content or f"我需要调用 {tool_names} 工具，但输出被截断了。",
        }
        user_msg = {
            "role": "user",
            "content": (
                "你的上一次回复因为太长被截断了，工具调用参数不完整。"
                "请用更简洁的方式重新生成。具体建议：\n"
                "1. 如果是生成代码/脚本，请将内容拆分为多个步骤，先完成核心部分\n"
                "2. 减少注释和装饰性内容\n"
                "3. 如果是生成报告，先生成简要版本"
            ),
        }
        warning_text = f"\n\n⚠️ 生成内容过长被截断，正在重新生成（第 {retry_count} 次）...\n\n"
        return assistant_msg, user_msg, warning_text

    # ────────────────────── 截断类型判断 ──────────────────────

    @staticmethod
    def classify_truncation(
        content: str,
        step_count: int,
        success_count: int,
        retry_count: int,
        max_retries: int,
    ) -> Dict[str, Any]:
        """
        分析截断的 LLM 输出，决定恢复策略。

        Returns:
            {
                "strategy": "finish_as_complete" | "inject_split_hint" | "inject_format_hint" | "retry" | "finish_as_text",
                "hint": str (注入给下一轮的提示),
                "finish_params": dict (如果策略是 finish_*),
            }
        """
        is_last_retry = retry_count >= max_retries - 1

        # 策略1: 多步且足够成功 → 直接视为完成
        if (step_count >= 5 and success_count >= 3) or (is_last_retry and step_count >= 8 and success_count >= 6):
            return {
                "strategy": "finish_as_complete",
                "hint": "",
                "finish_params": {
                    "summary": "任务已执行多步。请检查桌面或目标路径是否已有生成内容。",
                    "success": True,
                },
            }

        # 策略2: 截断的 JSON action（含 "action_type" 关键字）→ 注入拆分提示
        if '"action_type"' in content:
            return {
                "strategy": "inject_split_hint",
                "hint": (
                    "【输出被截断警告】你上次尝试输出了过大的 JSON，导致被截断。"
                    "请将大文件内容拆分：使用 create_and_run_script 编写 Python 脚本生成文件，"
                    "或使用 run_shell 通过 cat << 'HEREDOC' 写入。禁止在 write_file 中放入超长内容。"
                ),
            }

        return {"strategy": "retry", "hint": ""}

    # ────────────────────── JSON-like 内容判断 ──────────────────────

    @staticmethod
    def looks_like_json_or_code(content: str) -> bool:
        """判断内容是否疑似 JSON 或代码块（但解析失败了）。"""
        text = content.strip()
        if text.startswith("{") or text.startswith("["):
            return True
        if "```" in text:
            return True
        if '"action_type"' in text or '"params"' in text:
            return True
        return False

    # ────────────────────── 纯文本降级 ──────────────────────

    @staticmethod
    def handle_plain_text_response(
        content: str,
        step_count: int,
        retry_count: int,
        max_retries: int,
    ) -> Dict[str, Any]:
        """
        处理 LLM 返回纯文本（非 JSON）的情况。

        Returns:
            {
                "strategy": "reject_retry" | "accept_as_finish",
                "finish_params": dict (如果策略是 accept_as_finish),
            }
        """
        text = content.strip()[:4000]
        is_last_retry = retry_count >= max_retries - 1

        # 第一步长文本 + 不是最后一次重试 → 拒绝，重试强提示 JSON
        if step_count == 0 and len(text) > FIRST_STEP_PLAIN_TEXT_MIN_LEN and not is_last_retry:
            return {"strategy": "reject_retry"}

        # 其他情况：接受为 finish
        return {
            "strategy": "accept_as_finish",
            "finish_params": {"summary": text, "success": True},
        }

    # ────────────────────── write_file 截断检测 ──────────────────────

    @staticmethod
    def detect_write_file_truncation(content: str) -> Optional[str]:
        """
        检测 write_file 的 content（如 HTML）被截断的情况。
        返回降级提示，或 None。
        """
        has_indicators = (
            '"write_file"' in content and '"path"' in content
            and ('"content"' in content or "'content'" in content)
            and ("<!DOCTYPE" in content or "<html" in content or "html" in content.lower())
        )
        if has_indicators and len(content) > 2000:
            return (
                "【输出被截断】你上次尝试在 write_file 的 content 中放入超长 HTML，导致 JSON 被截断无法解析。"
                "**必须**改用 create_and_run_script：编写 Python 脚本，在脚本中用变量存储 HTML 字符串，"
                "然后 with open(path,'w') as f: f.write(html) 写入文件。禁止在 JSON 的 content 中直接放超长内容。"
            )
        return None

    # ────────────────────── JSON 格式提示 ──────────────────────

    @staticmethod
    def build_json_format_hint() -> str:
        """构建 JSON 格式错误提示。"""
        return (
            "【JSON 格式错误】你的上一步输出包含了代码块或 JSON，但系统无法正确解析。"
            "请直接输出一个纯 JSON 对象，不要用 ```json 代码块包裹，不要在 JSON 前后添加任何说明文字。"
            '{"action_type": "write_file", "params": {"path": "/path/to/file", "content": "..."}, "reasoning": "..."}'
        )
