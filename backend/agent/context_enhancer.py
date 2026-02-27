"""
LLM-Enhanced Context Retriever
Uses local LLM to improve context extraction from conversation history
"""

import logging
import asyncio
import time
from typing import List, Dict, Any, Optional

from .local_llm_manager import get_local_llm_manager, LocalLLMProvider
from .llm_utils import extract_text_from_content

logger = logging.getLogger(__name__)

# 连续超时后的冷却策略
_MAX_CONSECUTIVE_TIMEOUTS = 3
_COOLDOWN_SECONDS = 300  # 连续超时 N 次后冷却 5 分钟，不再调用本地 LLM


class ContextEnhancer:
    """
    Uses local LLM to enhance context retrieval
    - Analyzes user intent
    - Identifies task continuations
    - Extracts key information from history
    """

    INTENT_ANALYSIS_PROMPT = """分析用户查询意图，判断是否引用之前的任务。
用户查询: {query}
以JSON回答：{{"is_continuation":true/false,"task_keywords":["词1"],"time_reference":"recent/specific/none","search_terms":["词1"]}}
只输出JSON。"""

    CONTEXT_SUMMARY_PROMPT = """根据以下对话历史，提取与当前查询最相关的信息摘要。

当前查询: {query}

对话历史:
{history}

请提取：
1. 与当前查询相关的关键任务
2. 重要的上下文信息
3. 未完成的操作

以简洁的中文输出摘要（100字以内）。"""

    def __init__(self):
        self._llm_manager = get_local_llm_manager()
        self._consecutive_timeouts = 0
        self._cooldown_until: float = 0

    async def analyze_intent(self, query: str) -> Dict[str, Any]:
        """
        Analyze user query intent using local LLM.
        Includes cooldown logic: after N consecutive timeouts, skip LLM calls for a period.
        """
        # 冷却期内直接跳过，避免每次请求都等 15 秒超时
        if self._consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS:
            if time.time() < self._cooldown_until:
                logger.debug(
                    f"Intent analysis in cooldown ({self._consecutive_timeouts} consecutive timeouts), "
                    f"using keyword fallback"
                )
                return self._default_intent(query)
            # 冷却结束，重置计数器，再试一次
            self._consecutive_timeouts = 0

        try:
            client, config = await self._llm_manager.get_client()

            if client is None or config.provider == LocalLLMProvider.NONE:
                logger.debug("No local LLM available for intent analysis")
                return self._default_intent(query)

            # 优先选择较小的模型（7B 级别）做意图分析，14B 太慢
            model_name = config.model
            all_configs = self._llm_manager._all_configs
            if all_configs:
                from .local_llm_manager import LocalLLMManager
                small_chat = [
                    c for c in all_configs
                    if LocalLLMManager._is_chat_model(c.model)
                    and LocalLLMManager._estimate_model_size(c.model) <= 8
                ]
                if small_chat:
                    model_name = small_chat[0].model

            prompt = self.INTENT_ANALYSIS_PROMPT.format(query=query)

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=120,
                ),
                timeout=15.0,
            )

            raw = getattr(response.choices[0].message, "content", None)
            content = extract_text_from_content(raw).strip()

            import json
            if "{" in content and "}" in content:
                json_start = content.index("{")
                json_end = content.rindex("}") + 1
                result = json.loads(content[json_start:json_end])
                logger.info(f"Intent analysis: {result}")
                self._consecutive_timeouts = 0
                return result

        except asyncio.TimeoutError:
            self._consecutive_timeouts += 1
            self._cooldown_until = time.time() + _COOLDOWN_SECONDS
            logger.warning(
                f"Intent analysis timed out (15s), consecutive={self._consecutive_timeouts}. "
                f"{'Entering cooldown.' if self._consecutive_timeouts >= _MAX_CONSECUTIVE_TIMEOUTS else ''}"
            )
            if self._consecutive_timeouts == 1:
                try:
                    from .system_message_service import get_system_message_service, MessageCategory
                    get_system_message_service().add_warning(
                        "意图分析超时",
                        "本地 LLM 意图分析超时，已使用默认关键词匹配。如持续超时将自动跳过。",
                        source="context_enhancer",
                        category=MessageCategory.INFO.value,
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}")

        return self._default_intent(query)
    
    def _default_intent(self, query: str) -> Dict[str, Any]:
        """Default intent analysis without LLM"""
        # 简单的关键词检测
        continuation_keywords = [
            "继续", "接着", "之前", "刚才", "上次", "那个",
            "continue", "previous", "last", "earlier"
        ]
        
        is_continuation = any(kw in query.lower() for kw in continuation_keywords)
        
        return {
            "is_continuation": is_continuation,
            "task_keywords": query.split()[:5],
            "time_reference": "recent" if is_continuation else "none",
            "search_terms": query.split()[:3]
        }
    
    async def summarize_context(
        self, 
        query: str, 
        history: List[Dict[str, Any]],
        max_history: int = 10
    ) -> Optional[str]:
        """
        Summarize relevant context from conversation history
        Uses local LLM to extract key information
        """
        if not history:
            return None
        
        try:
            client, config = await self._llm_manager.get_client()
            
            if client is None or config.provider == LocalLLMProvider.NONE:
                return None
            
            # 格式化历史
            history_text = ""
            for msg in history[-max_history:]:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:300]  # 截断长内容
                history_text += f"{role}: {content}\n\n"
            
            prompt = self.CONTEXT_SUMMARY_PROMPT.format(
                query=query,
                history=history_text
            )
            
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=150
                ),
                timeout=15.0
            )
            
            raw = getattr(response.choices[0].message, "content", None)
            summary = extract_text_from_content(raw).strip()
            logger.info(f"Context summary generated: {summary[:50]}...")
            return summary
            
        except asyncio.TimeoutError:
            logger.warning("Context summarization timed out")
        except Exception as e:
            logger.warning(f"Context summarization failed: {e}")
        
        return None
    
    async def enhance_query(self, query: str, history: List[Dict[str, Any]]) -> str:
        """
        Enhance a vague query using context from history
        Returns the enhanced query or original if enhancement fails
        """
        intent = await self.analyze_intent(query)
        
        if not intent.get("is_continuation"):
            return query
        
        # 尝试从历史中找到相关任务
        if history:
            # 找到最近的用户任务描述
            for msg in reversed(history):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    # 跳过类似"继续"的短消息
                    if len(content) > 20 and not any(kw in content for kw in ["继续", "接着"]):
                        # 找到了之前的任务
                        enhanced = f"{query}\n\n[之前的任务: {content[:200]}]"
                        logger.info(f"Query enhanced with previous task context")
                        return enhanced
        
        return query


# Global instance
_context_enhancer: Optional[ContextEnhancer] = None


def get_context_enhancer() -> ContextEnhancer:
    """Get or create global context enhancer"""
    global _context_enhancer
    if _context_enhancer is None:
        _context_enhancer = ContextEnhancer()
    return _context_enhancer
