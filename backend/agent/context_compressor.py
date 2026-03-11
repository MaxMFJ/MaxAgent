"""
Context Compressor — 智能上下文压缩
在 token 预算内保留最重要的信息，淘汰冗余内容。

策略：
1. 保留: system prompt、最近 N 轮对话、当前 user 消息
2. 压缩: 旧的 tool 输出 → 摘要
3. 淘汰: 重复信息、过长的中间结果
4. 语义: 保留与当前任务最相关的历史片段
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 默认 token 预算（近似，1 token ≈ 2 中文字符 / 4 英文字符）
DEFAULT_MAX_TOKENS = 12000
CHARS_PER_TOKEN = 3  # 中英混合近似


class ContextCompressor:
    """
    上下文压缩器。
    接收消息列表，按策略压缩到 token 预算内。
    """

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.max_tokens = max_tokens

    def compress(
        self,
        messages: List[Dict[str, Any]],
        current_query: str = "",
        keep_recent: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        压缩消息列表到 token 预算内。

        Args:
            messages:      完整消息列表
            current_query: 当前 user 查询（确保不丢失）
            keep_recent:   保留最近 N 条消息不压缩

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        total_chars = sum(len(m.get("content", "")) for m in messages)
        budget_chars = self.max_tokens * CHARS_PER_TOKEN

        # 未超预算，不压缩
        if total_chars <= budget_chars:
            return messages

        logger.info(
            "Context compression: %d msgs, %d chars → budget %d chars",
            len(messages), total_chars, budget_chars,
        )

        # Step 1: 分离 system / 保护区 / 可压缩区
        system_msgs, protected, compressible = self._partition(
            messages, keep_recent
        )

        # Step 2: 压缩可压缩区
        compressed = self._compress_messages(compressible, budget_chars, system_msgs, protected)

        # Step 3: 组装结果
        result = system_msgs + compressed + protected

        # Step 4: 确保当前 query 在最后
        if current_query:
            result = self._ensure_query(result, current_query)

        final_chars = sum(len(m.get("content", "")) for m in result)
        logger.info(
            "Compression result: %d msgs, %d chars (saved %.0f%%)",
            len(result), final_chars,
            (1 - final_chars / max(total_chars, 1)) * 100,
        )
        return result

    def compress_action_logs(
        self,
        action_logs: List[Dict[str, Any]],
        max_entries: int = 15,
    ) -> str:
        """
        压缩 action_logs 为 LLM 可读的摘要。
        用于注入到 prompt 中替代完整历史。
        """
        if not action_logs:
            return ""

        if len(action_logs) <= max_entries:
            return self._format_logs(action_logs)

        # 保留最近的 + 失败的 + 首尾
        recent = action_logs[-max_entries // 2:]
        failures = [
            log for log in action_logs[:-len(recent)]
            if not log.get("result", {}).get("success", True)
        ][:max_entries // 4]
        first = action_logs[:2]

        selected = first + failures + recent
        # 去重保持顺序
        seen = set()
        unique = []
        for log in selected:
            key = log.get("action", {}).get("action_id", id(log))
            if key not in seen:
                seen.add(key)
                unique.append(log)

        header = f"[执行历史摘要: 共 {len(action_logs)} 步，显示 {len(unique)} 步关键节点]\n"
        return header + self._format_logs(unique)

    def compress_tool_output(self, output: str, max_chars: int = 500) -> str:
        """压缩单个 tool 输出"""
        if not output or len(output) <= max_chars:
            return output

        # 文件列表类输出：保留前 N 行
        lines = output.split("\n")
        if len(lines) > 20:
            kept = lines[:10] + [f"... ({len(lines) - 15} 行省略) ..."] + lines[-5:]
            result = "\n".join(kept)
            if len(result) <= max_chars:
                return result

        # 通用截断
        half = max_chars // 2
        return output[:half] + f"\n... [截断 {len(output) - max_chars} 字符] ...\n" + output[-half:]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _partition(
        self,
        messages: List[Dict[str, Any]],
        keep_recent: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        分区:
        - system_msgs:  所有 role=system 消息
        - protected:    最近 keep_recent 条非 system 消息（不压缩）
        - compressible: 其余消息（可压缩）
        """
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= keep_recent:
            return system_msgs, non_system, []

        protected = non_system[-keep_recent:]
        compressible = non_system[:-keep_recent]
        return system_msgs, protected, compressible

    def _compress_messages(
        self,
        compressible: List[Dict[str, Any]],
        budget_chars: int,
        system_msgs: List[Dict[str, Any]],
        protected: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """压缩可压缩区的消息"""
        # 已占用的 chars
        used = (
            sum(len(m.get("content", "")) for m in system_msgs) +
            sum(len(m.get("content", "")) for m in protected)
        )
        remaining = budget_chars - used
        if remaining <= 0:
            # 甚至保护区都超预算了，返回一条摘要
            return self._summarize_as_single(compressible)

        result = []
        chars_used = 0

        for msg in compressible:
            content = msg.get("content", "")
            role = msg.get("role", "")

            # Tool 输出：激进压缩
            if role == "tool" or (role == "assistant" and self._looks_like_tool_output(content)):
                compressed = self.compress_tool_output(content, max_chars=200)
                if chars_used + len(compressed) <= remaining:
                    result.append({"role": role, "content": compressed})
                    chars_used += len(compressed)
                continue

            # User/Assistant 消息：适度压缩
            if len(content) > 300:
                content = content[:200] + f"... [{len(content)} 字符]"

            if chars_used + len(content) <= remaining:
                result.append({"role": role, "content": content})
                chars_used += len(content)
            else:
                # 预算用完，剩余消息合并为摘要
                remaining_msgs = compressible[compressible.index(msg):]
                summary = self._summarize_as_single(remaining_msgs)
                result.extend(summary)
                break

        return result

    def _summarize_as_single(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将多条消息合并为一条摘要"""
        if not messages:
            return []
        roles = {}
        for m in messages:
            role = m.get("role", "unknown")
            roles[role] = roles.get(role, 0) + 1
        role_desc = ", ".join(f"{r}×{c}" for r, c in roles.items())
        return [{
            "role": "system",
            "content": f"[上下文摘要: 省略了 {len(messages)} 条历史消息 ({role_desc})。最近对话已完整保留。]"
        }]

    def _looks_like_tool_output(self, content: str) -> bool:
        """判断内容是否像 tool 输出"""
        if not content:
            return False
        indicators = [
            content.startswith("{") and "success" in content[:100],
            content.startswith("["),
            "exit_code" in content[:200],
            content.startswith("```"),
            "[Verify]" in content[:50],
        ]
        return any(indicators)

    def _ensure_query(
        self, messages: List[Dict[str, Any]], current_query: str,
    ) -> List[Dict[str, Any]]:
        """确保当前 user 查询在末尾"""
        if not messages:
            return [{"role": "user", "content": current_query}]
        last = messages[-1]
        if last.get("role") == "user" and current_query[:50] in last.get("content", "")[:60]:
            return messages
        messages.append({"role": "user", "content": current_query})
        return messages

    def _format_logs(self, logs: List[Dict[str, Any]]) -> str:
        """格式化 action logs"""
        parts = []
        for log in logs:
            action = log.get("action", {})
            result = log.get("result", {})
            at = action.get("action_type", "?")
            success = "✅" if result.get("success") else "❌"
            line = f"{success} {at}"
            output = result.get("output", "")
            if output and isinstance(output, str):
                line += f": {output[:80]}"
            error = result.get("error", "")
            if error:
                line += f" [err: {error[:60]}]"
            parts.append(line)
        return "\n".join(parts)


# 单例
_compressor: Optional[ContextCompressor] = None


def get_context_compressor(max_tokens: int = DEFAULT_MAX_TOKENS) -> ContextCompressor:
    global _compressor
    if _compressor is None:
        _compressor = ContextCompressor(max_tokens=max_tokens)
    return _compressor
