"""
Context Manager for Agent Conversations
Manages conversation history with vector-based semantic retrieval
"""

import os
import json
import logging
import uuid
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
    created_files: List[str] = field(default_factory=list)  # 本会话中通过工具创建/写入的文件绝对路径
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    # 配置
    max_recent_messages: int = 10  # 内存中保留最近的消息数
    use_vector_search: bool = True  # 启用向量搜索
    max_context_tokens: int = 8000  # 发送给 LLM 的上下文最大 token 数（默认聊天/轻量问答）
    
    # 任务类型到 max_context_tokens 的映射（由外部通过 set_task_tier 设置）
    _TIER_TOKEN_MAP = {
        "simple": 8000,       # 聊天/轻量问答
        "complex": 32000,     # 默认 Agent 任务
        "json_probe": 60000,  # JSON consistency / probe
        "long_doc": 80000,    # 超长文档生成
    }
    
    def __post_init__(self):
        self._vector_store: Optional[VectorMemoryStore] = None
        self._vector_store_synced: bool = False  # 标记是否已从 recent_messages 同步到 vector_store
        self._current_task_tier: str = "simple"  # 当前任务层级
    
    def set_task_tier(self, tier: str) -> None:
        """
        根据任务类型动态调整 max_context_tokens。
        tier: 'simple' | 'complex' | 'json_probe' | 'long_doc'
        """
        self._current_task_tier = tier
        new_limit = self._TIER_TOKEN_MAP.get(tier, 8000)
        if new_limit != self.max_context_tokens:
            self.max_context_tokens = new_limit
            logger.info(f"Session {self.session_id}: max_context_tokens set to {new_limit} for tier '{tier}'")
    
    def _sync_recent_to_vector_store(self) -> None:
        """
        将 recent_messages 同步到 vector_store。
        用于从磁盘加载会话时，确保 BGE 向量检索有完整历史可搜，避免长对话丢失上下文。
        """
        if self._vector_store_synced or not self.recent_messages or not self.use_vector_search:
            return
        try:
            vs = self.vector_store
            for msg in self.recent_messages:
                role = msg.get("role")
                content = msg.get("content")
                if role and content and content.strip():
                    vs.add(role, content.strip())
            self._vector_store_synced = True
            logger.info(f"Synced {len(self.recent_messages)} messages to vector store for session {self.session_id}")
        except Exception as e:
            logger.warning(f"Failed to sync recent_messages to vector store: {e}")
    
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
        
        msg = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.now(),
            **kwargs
        }
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
    
    def add_created_file(self, path: str) -> None:
        """记录本会话中通过工具创建/写入的文件路径（用于后续追问时 LLM 能告知用户位置）"""
        if not path or not path.strip():
            return
        abs_path = os.path.abspath(os.path.expanduser(path.strip()))
        if abs_path not in self.created_files:
            self.created_files.append(abs_path)
            logger.info(f"Session {self.session_id}: recorded created file {abs_path}")

    def add_duck_output(
        self,
        task_id: str,
        duck_type: str,
        duck_id: str,
        description_preview: str,
        file_paths: list,
        summary: str,
    ) -> None:
        """
        记录 Duck 子任务的产出（文件路径 + 摘要）到 Duck 工作区。
        主 Agent 再次运行时可通过 get_duck_workspace_hint() 获取所有已完成 Duck 的产出，
        用于在后续任务中引用（如把设计图路径传给 coder Duck）。
        """
        if not hasattr(self, "_duck_workspace"):
            self._duck_workspace: list = []
        entry = {
            "task_id": task_id,
            "duck_type": duck_type,
            "duck_id": duck_id,
            "description_preview": description_preview[:80],
            "file_paths": file_paths,
            "summary": summary[:300],
        }
        self._duck_workspace.append(entry)
        # 同时注册到 created_files，确保系统提示携带路径
        for p in file_paths:
            self.add_created_file(p)

    def get_duck_workspace_hint(self) -> str:
        """
        返回当前会话中所有 Duck 子任务产出的摘要字符串，用于注入主 Agent 的续步提示。
        """
        workspace = getattr(self, "_duck_workspace", [])
        if not workspace:
            return ""
        lines = ["[Duck 任务工作区 — 以下是本次对话中所有 Duck 完成的任务产出：]"]
        for i, entry in enumerate(workspace, 1):
            dt = entry.get("duck_type", "?")
            paths = entry.get("file_paths", [])
            summary = entry.get("summary", "")
            desc = entry.get("description_preview", "")
            paths_str = ", ".join(f"`{p}`" for p in paths) if paths else "（无文件产出）"
            lines.append(f"{i}. [{dt} Duck] 任务：{desc}")
            lines.append(f"   产出文件：{paths_str}")
            if summary:
                lines.append(f"   摘要：{summary[:150]}")
        return "\n".join(lines)
    
    def get_context_messages(self, current_query: str = "") -> List[Dict[str, Any]]:
        """
        Get optimized context messages for LLM.
        Uses BGE 向量检索 + 最近消息，保证「纯追问」能看到完整历史，减少误判执行。
        企业级：与 query_classifier(intent=information) + execution_guard 配合使用。

        **防污染保护**：
        1. 向量检索采用 newest-first 策略，确保当前查询永远不被截断丢弃
        2. 末尾兜底检查：如果最后一条消息不是当前 user 消息，强制追加
        """
        logger.debug(f"get_context_messages called with {len(self.recent_messages)} recent messages, use_vector_search={self.use_vector_search}")
        
        try:
            if self.use_vector_search and current_query and len(self.recent_messages) > 3:
                # 从磁盘加载的会话：vector_store 为空，需先将 recent_messages 同步进去
                self._sync_recent_to_vector_store()
                # recent_count=6: 保留最近 6 条消息（3 轮对话）维持连贯性
                # semantic_count=3: 通过 BGE 语义检索补充最相关的历史片段
                context_messages = self.vector_store.get_context_messages(
                    current_query=current_query,
                    max_tokens=self.max_context_tokens,
                    recent_count=6,
                    semantic_count=3
                )
                
                # 保护：vector_store 返回过少（如 BGE 未加载、embedding 失败）时回退到 recent_messages
                min_expected = min(4, len(self.recent_messages))
                if context_messages and len(context_messages) >= min_expected:
                    result = []
                    if len(context_messages) > self.max_recent_messages:
                        result.append({
                            "role": "system",
                            "content": "[以下是与当前问题相关的历史对话上下文]"
                        })
                    result.extend(context_messages)
                    # 防污染：确保当前 user 查询一定在最后
                    result = self._ensure_current_query_present(result, current_query)
                    logger.info(f"Returning {len(result)} messages from vector search")
                    return result
                elif context_messages:
                    logger.debug(
                        f"Vector search returned only {len(context_messages)} msgs (expected >= {min_expected}), "
                        f"falling back to recent_messages"
                    )
        except Exception as e:
            logger.warning(f"Vector search failed, using recent messages: {e}")
        
        # 回退：返回最近的消息（移除 timestamp 等非标准字段）
        fallback_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.recent_messages
            if msg.get("content")
        ]
        # 防污染：确保当前 user 查询一定在最后
        fallback_messages = self._ensure_current_query_present(fallback_messages, current_query)
        logger.info(f"Returning {len(fallback_messages)} messages from recent_messages fallback")
        return fallback_messages
    
    def _ensure_current_query_present(
        self, messages: List[Dict[str, Any]], current_query: str
    ) -> List[Dict[str, Any]]:
        """
        防污染兜底：确保消息列表的最后一条是当前 user 查询。
        如果因为 token 预算截断导致当前查询被丢弃，这里会强制追加。
        """
        if not current_query or not current_query.strip():
            return messages
        
        # 检查最后一条 user 消息是否就是当前查询
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                last_user_idx = i
                break
        
        if last_user_idx >= 0:
            last_user_content = messages[last_user_idx].get("content", "")
            # 如果最后一条 user 消息就是当前查询（或其截断版本），无需追加
            if current_query.strip().startswith(last_user_content[:50].strip()):
                return messages
            if last_user_content.strip().startswith(current_query[:50].strip()):
                return messages
        
        # 当前查询不在末尾或完全缺失，强制追加
        logger.warning(
            f"Session {self.session_id}: current user query was missing from context, "
            f"force-appending to prevent stale response"
        )
        messages.append({"role": "user", "content": current_query})
        return messages
    
    def clear(self):
        """Clear conversation history"""
        self.recent_messages = []
        self.created_files = []
        self._vector_store_synced = False
        if self._vector_store:
            self._vector_store.clear()
        clear_vector_store(self.session_id)


class ContextManager:
    """Manages multiple conversation contexts with persistence"""
    
    def __init__(self, max_sessions: int = 100):
        self.sessions: Dict[str, ConversationContext] = {}
        self.max_sessions = max_sessions
        from paths import DATA_DIR
        self._storage_dir = os.path.join(DATA_DIR, "contexts")
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
                "created_files": context.created_files,
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
            context.created_files = data.get("created_files", [])
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
    
    def set_session_task_tier(self, session_id: str, tier: str) -> None:
        """
        设置会话的任务层级，动态调整 max_context_tokens。
        tier: 'simple' | 'complex' | 'json_probe' | 'long_doc'
        """
        ctx = self.get_or_create(session_id)
        ctx.set_task_tier(tier)
    
    def delete_session(self, session_id: str):
        """Delete a session entirely"""
        if session_id in self.sessions:
            del self.sessions[session_id]


# 全局上下文管理器
context_manager = ContextManager()
