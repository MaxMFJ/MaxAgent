"""
Context Manager for Agent Conversations
Manages conversation history with vector-based semantic retrieval
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .vector_store import get_vector_store, clear_vector_store, VectorMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """
    Stores context for a conversation session
    Uses vector store for semantic retrieval to reduce token consumption
    """
    session_id: str
    recent_messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    # 配置
    max_recent_messages: int = 10  # 内存中保留最近的消息数
    use_vector_search: bool = True  # 启用向量搜索
    max_context_tokens: int = 2000  # 发送给 LLM 的上下文最大 token 数（从 3000 降低）
    
    def __post_init__(self):
        self._vector_store: Optional[VectorMemoryStore] = None
    
    @property
    def vector_store(self) -> VectorMemoryStore:
        """懒加载向量存储"""
        if self._vector_store is None:
            self._vector_store = get_vector_store(self.session_id)
        return self._vector_store
    
    @property
    def messages(self) -> List[Dict[str, Any]]:
        """兼容旧接口"""
        return self.recent_messages
    
    def add_message(self, role: str, content: str, **kwargs):
        """Add a message to the context"""
        if not content or not content.strip():
            return
        
        # 过滤掉"上下文丢失"类型的错误回复，避免污染历史记录
        if role == "assistant":
            error_indicators = [
                "无法看到之前的对话历史",
                "无法看到之前的对话",
                "我不知道之前的任务",
                "没有之前的对话上下文",
                "我需要更多信息来了解具体是什么任务",
                "之前我们在处理什么任务",
            ]
            for indicator in error_indicators:
                if indicator in content:
                    logger.warning(f"Filtering out context-loss error response: {content[:50]}...")
                    return
        
        msg = {"role": role, "content": content, "timestamp": datetime.now(), **kwargs}
        self.recent_messages.append(msg)
        self.last_active = datetime.now()
        
        # 同时添加到向量存储（异步，不阻塞）
        if self.use_vector_search:
            try:
                self.vector_store.add(role, content, **kwargs)
            except Exception as e:
                logger.warning(f"Failed to add to vector store: {e}")
        
        # 保持最近消息数量
        if len(self.recent_messages) > self.max_recent_messages:
            self.recent_messages = self.recent_messages[-self.max_recent_messages:]
    
    def get_context_messages(self, current_query: str = "") -> List[Dict[str, Any]]:
        """
        Get optimized context messages for LLM
        Uses semantic search to find relevant historical context
        """
        logger.debug(f"get_context_messages called with {len(self.recent_messages)} recent messages, use_vector_search={self.use_vector_search}")
        
        try:
            if self.use_vector_search and current_query and len(self.recent_messages) > 3:
                # recent_count=4: 保留最近 4 条消息（2 轮对话）维持连贯性
                # semantic_count=3: 通过 BGE 语义检索补充最相关的历史片段
                # 这样 BGE 真正发挥裁剪作用，而非返回全部历史
                context_messages = self.vector_store.get_context_messages(
                    current_query=current_query,
                    max_tokens=self.max_context_tokens,
                    recent_count=4,
                    semantic_count=3
                )
                
                if context_messages:
                    result = []
                    # 添加上下文提示
                    if len(context_messages) > self.max_recent_messages:
                        result.append({
                            "role": "system",
                            "content": "[以下是与当前问题相关的历史对话上下文]"
                        })
                    
                    result.extend(context_messages)
                    logger.info(f"Returning {len(result)} messages from vector search")
                    return result
                else:
                    logger.debug("Vector search returned empty, falling back to recent_messages")
        except Exception as e:
            logger.warning(f"Vector search failed, using recent messages: {e}")
        
        # 回退：返回最近的消息（移除 timestamp 等非标准字段）
        fallback_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.recent_messages
            if msg.get("content")
        ]
        logger.info(f"Returning {len(fallback_messages)} messages from recent_messages fallback")
        return fallback_messages
    
    def clear(self):
        """Clear conversation history"""
        self.recent_messages = []
        if self._vector_store:
            self._vector_store.clear()
        clear_vector_store(self.session_id)


class ContextManager:
    """Manages multiple conversation contexts with persistence"""
    
    def __init__(self, max_sessions: int = 100):
        self.sessions: Dict[str, ConversationContext] = {}
        self.max_sessions = max_sessions
        self._storage_dir = os.path.join(os.path.dirname(__file__), "..", "data", "contexts")
        os.makedirs(self._storage_dir, exist_ok=True)
    
    def get_or_create(self, session_id: str) -> ConversationContext:
        """Get existing context or create new one"""
        if session_id not in self.sessions:
            # 尝试从磁盘加载
            loaded = self._load_from_disk(session_id)
            if loaded:
                self.sessions[session_id] = loaded
                logger.info(f"Loaded context from disk for session: {session_id}")
            else:
                # 清理旧会话
                if len(self.sessions) >= self.max_sessions:
                    self._cleanup_old_sessions()
                
                self.sessions[session_id] = ConversationContext(session_id=session_id)
                logger.info(f"Created new context for session: {session_id}")
        
        return self.sessions[session_id]
    
    def save_session(self, session_id: str):
        """Save session to disk"""
        if session_id in self.sessions:
            self._save_to_disk(session_id, self.sessions[session_id])
    
    def _save_to_disk(self, session_id: str, context: ConversationContext):
        """Persist context to disk"""
        try:
            import json
            filepath = os.path.join(self._storage_dir, f"{session_id}.json")
            data = {
                "session_id": context.session_id,
                "recent_messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in context.recent_messages
                    if m.get("content")
                ],
                "created_at": context.created_at.isoformat(),
                "last_active": context.last_active.isoformat()
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save context to disk: {e}")
    
    def _load_from_disk(self, session_id: str) -> Optional[ConversationContext]:
        """Load context from disk"""
        try:
            import json
            filepath = os.path.join(self._storage_dir, f"{session_id}.json")
            logger.debug(f"Looking for context file: {filepath}")
            
            if not os.path.exists(filepath):
                logger.debug(f"Context file not found: {filepath}")
                return None
            
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            context = ConversationContext(session_id=session_id)
            context.recent_messages = data.get("recent_messages", [])
            context.created_at = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
            context.last_active = datetime.fromisoformat(data.get("last_active", datetime.now().isoformat()))
            
            logger.info(f"Loaded {len(context.recent_messages)} messages from disk for session: {session_id}")
            return context
        except Exception as e:
            logger.warning(f"Failed to load context from disk: {e}", exc_info=True)
            return None
    
    def _cleanup_old_sessions(self):
        """Remove oldest sessions"""
        if not self.sessions:
            return
        
        # 按最后活动时间排序，删除最旧的
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: x[1].last_active
        )
        
        # 删除一半的旧会话
        remove_count = len(sorted_sessions) // 2
        for session_id, _ in sorted_sessions[:remove_count]:
            del self.sessions[session_id]
        
        logger.info(f"Cleaned up {remove_count} old sessions")
    
    def clear_session(self, session_id: str):
        """Clear a specific session"""
        if session_id in self.sessions:
            self.sessions[session_id].clear()
    
    def delete_session(self, session_id: str):
        """Delete a session entirely"""
        if session_id in self.sessions:
            del self.sessions[session_id]


# 全局上下文管理器
context_manager = ContextManager()
