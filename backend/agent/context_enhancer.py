"""
LLM-Enhanced Context Retriever
Uses local LLM to improve context extraction from conversation history
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional

from .local_llm_manager import get_local_llm_manager, LocalLLMProvider

logger = logging.getLogger(__name__)


class ContextEnhancer:
    """
    Uses local LLM to enhance context retrieval
    - Analyzes user intent
    - Identifies task continuations
    - Extracts key information from history
    """
    
    INTENT_ANALYSIS_PROMPT = """分析用户的查询意图，判断是否在引用之前的任务或对话。

用户查询: {query}

请以 JSON 格式回答：
{{
  "is_continuation": true/false,  // 是否在继续之前的任务
  "task_keywords": ["关键词1", "关键词2"],  // 可能相关的任务关键词
  "time_reference": "recent/specific/none",  // 时间引用：最近的/特定的/无
  "search_terms": ["搜索词1", "搜索词2"]  // 用于搜索历史的关键词
}}

只输出 JSON，不要其他内容。"""

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
    
    async def analyze_intent(self, query: str) -> Dict[str, Any]:
        """
        Analyze user query intent using local LLM
        Returns intent analysis with keywords for context search
        """
        try:
            client, config = await self._llm_manager.get_client()
            
            if client is None or config.provider == LocalLLMProvider.NONE:
                logger.debug("No local LLM available for intent analysis")
                return self._default_intent(query)
            
            prompt = self.INTENT_ANALYSIS_PROMPT.format(query=query)
            
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=200
                ),
                timeout=10.0
            )
            
            content = response.choices[0].message.content.strip()
            
            # 解析 JSON
            import json
            # 尝试提取 JSON
            if "{" in content and "}" in content:
                json_start = content.index("{")
                json_end = content.rindex("}") + 1
                json_str = content[json_start:json_end]
                result = json.loads(json_str)
                logger.info(f"Intent analysis: {result}")
                return result
            
        except asyncio.TimeoutError:
            logger.warning("Intent analysis timed out")
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
            
            summary = response.choices[0].message.content.strip()
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
