"""
Vector Store for Semantic Context Management
Uses BGE embedding models for efficient context retrieval
"""

import os
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

# 配置
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")  # 默认使用小模型，更快
ENABLE_VECTOR_SEARCH = os.getenv("ENABLE_VECTOR_SEARCH", "true").lower() == "true"

# 延迟加载，避免启动时间过长
_embedding_model = None
_model_loading = False


def _get_embedding_device() -> str:
    """
    获取嵌入模型使用的设备。
    在 Apple Silicon 上强制使用 CPU，避免 MPS 在 SDPA 上的已知崩溃：
    validateComputeFunctionArguments sdpa_vector_float_64_64 buffer size mismatch
    """
    try:
        import torch
        if torch.backends.mps.is_available() and torch.backends.mps.is_built():
            return "cpu"  # 强制 CPU，避免 MPS SDPA 崩溃
    except Exception:
        pass
    return "cpu"


def get_embedding_model():
    """懒加载嵌入模型"""
    global _embedding_model, _model_loading
    
    if not ENABLE_VECTOR_SEARCH:
        return None
    
    # 如果正在加载，返回 None（不阻塞）
    if _model_loading:
        logger.debug("Model is loading, skipping embedding")
        return None
    
    if _embedding_model is None:
        _model_loading = True
        try:
            from sentence_transformers import SentenceTransformer
            
            model_name = EMBEDDING_MODEL
            device = _get_embedding_device()
            logger.info(f"Loading embedding model: {model_name} on {device}...")
            
            # 模型选项：
            # - BAAI/bge-m3: 最强，支持多语言，但较大 (~1.5GB)
            # - BAAI/bge-large-zh-v1.5: 中文优秀 (~1.3GB)
            # - BAAI/bge-small-zh-v1.5: 中文，小而快 (~90MB) [默认]
            # - BAAI/bge-base-zh-v1.5: 中文，平衡选择 (~400MB)
            #
            # 注意：Apple Silicon 上使用 device='cpu' 以避免 MPS SDPA 崩溃
            _embedding_model = SentenceTransformer(model_name, device=device)
            logger.info(f"Embedding model loaded: {model_name}, dim={_embedding_model.get_sentence_embedding_dimension()}")
            
        except Exception as e:
            logger.warning(f"Failed to load embedding model {EMBEDDING_MODEL}: {e}")
            # 尝试更小的模型
            try:
                from sentence_transformers import SentenceTransformer
                device = _get_embedding_device()
                _embedding_model = SentenceTransformer('BAAI/bge-small-zh-v1.5', device=device)
                logger.info(f"Loaded fallback model: bge-small-zh-v1.5 on {device}")
            except Exception as e2:
                logger.error(f"Failed to load any embedding model: {e2}")
                _embedding_model = None
        finally:
            _model_loading = False
    
    return _embedding_model


def preload_embedding_model():
    """预加载模型（可在启动时调用）"""
    import threading
    def _load():
        get_embedding_model()
    thread = threading.Thread(target=_load, daemon=True)
    thread.start()
    logger.info("Started background model loading")


@dataclass
class MemoryItem:
    """A single memory item with embedding"""
    id: str
    content: str
    role: str
    embedding: Optional[np.ndarray] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            **self.metadata
        }


class VectorMemoryStore:
    """
    Vector-based memory store for conversation context
    Uses semantic similarity to retrieve relevant context
    """
    
    def __init__(self, max_items: int = 100, similarity_threshold: float = 0.5):
        self.max_items = max_items
        self.similarity_threshold = similarity_threshold
        self.items: Dict[str, MemoryItem] = {}
        self._embeddings_matrix: Optional[np.ndarray] = None
        self._id_to_index: Dict[str, int] = {}
        self._dirty = True
    
    def _get_content_hash(self, content: str) -> str:
        """Generate hash for content deduplication"""
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _compute_embedding(self, text: str) -> Optional[np.ndarray]:
        """Compute embedding for text"""
        model = get_embedding_model()
        if model is None:
            return None
        
        try:
            # BGE 模型建议添加指令前缀
            embedding = model.encode(text, normalize_embeddings=True)
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            logger.error(f"Failed to compute embedding: {e}")
            return None
    
    def add(self, role: str, content: str, **metadata) -> Optional[str]:
        """Add a message to the memory store"""
        if not content or not content.strip():
            return None
        
        content = content.strip()
        item_id = self._get_content_hash(f"{role}:{content}")
        
        # 检查是否已存在
        if item_id in self.items:
            return item_id
        
        # 计算嵌入
        embedding = self._compute_embedding(content)
        
        item = MemoryItem(
            id=item_id,
            content=content,
            role=role,
            embedding=embedding,
            metadata=metadata
        )
        
        self.items[item_id] = item
        self._dirty = True
        
        # 限制数量
        if len(self.items) > self.max_items:
            self._evict_oldest()
        
        return item_id
    
    def _evict_oldest(self):
        """Remove oldest items when over capacity"""
        sorted_items = sorted(
            self.items.values(),
            key=lambda x: x.timestamp
        )
        
        # 删除最旧的 20%
        remove_count = max(1, len(sorted_items) // 5)
        for item in sorted_items[:remove_count]:
            del self.items[item.id]
        
        self._dirty = True
        logger.info(f"Evicted {remove_count} old memory items")
    
    def _rebuild_index(self):
        """Rebuild the embedding matrix for search"""
        if not self._dirty:
            return
        
        items_with_embeddings = [
            item for item in self.items.values()
            if item.embedding is not None
        ]
        
        if not items_with_embeddings:
            self._embeddings_matrix = None
            self._id_to_index = {}
            self._dirty = False
            return
        
        self._embeddings_matrix = np.vstack([
            item.embedding for item in items_with_embeddings
        ])
        
        self._id_to_index = {
            item.id: i for i, item in enumerate(items_with_embeddings)
        }
        
        self._dirty = False
    
    def search(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """Search for relevant memories using semantic similarity"""
        if not self.items:
            return []
        
        query_embedding = self._compute_embedding(query)
        if query_embedding is None:
            # 如果嵌入失败，返回最近的消息
            sorted_items = sorted(
                self.items.values(),
                key=lambda x: x.timestamp,
                reverse=True
            )
            return sorted_items[:top_k]
        
        self._rebuild_index()
        
        if self._embeddings_matrix is None:
            return list(self.items.values())[:top_k]
        
        # 计算余弦相似度
        similarities = np.dot(self._embeddings_matrix, query_embedding)
        
        # 获取 top_k 索引
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # 构建 index 到 item 的映射
        index_to_id = {v: k for k, v in self._id_to_index.items()}
        
        results = []
        for idx in top_indices:
            if idx in index_to_id:
                item_id = index_to_id[idx]
                if similarities[idx] >= self.similarity_threshold:
                    results.append(self.items[item_id])
        
        return results
    
    def get_recent(self, count: int = 5) -> List[MemoryItem]:
        """Get most recent memories"""
        sorted_items = sorted(
            self.items.values(),
            key=lambda x: x.timestamp,
            reverse=True
        )
        return sorted_items[:count]
    
    def clear(self):
        """Clear all memories"""
        self.items.clear()
        self._embeddings_matrix = None
        self._id_to_index = {}
        self._dirty = True
    
    def get_context_messages(
        self,
        current_query: str,
        max_tokens: int = 2000,
        recent_count: int = 3,
        semantic_count: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get optimized context messages for LLM
        Combines recent messages with semantically relevant ones
        """
        try:
            messages = []
            seen_ids = set()
            estimated_tokens = 0
            
            # 1. 先添加最近的消息（保持连贯性）
            recent = self.get_recent(recent_count)
            for item in reversed(recent):  # 按时间顺序
                if item.id not in seen_ids:
                    msg_tokens = len(item.content) // 2  # 粗略估计
                    if estimated_tokens + msg_tokens > max_tokens:
                        break
                    messages.append({"role": item.role, "content": item.content})
                    seen_ids.add(item.id)
                    estimated_tokens += msg_tokens
            
            # 2. 添加语义相关的消息
            if current_query:
                try:
                    relevant = self.search(current_query, top_k=semantic_count)
                    for item in relevant:
                        if item.id not in seen_ids:
                            msg_tokens = len(item.content) // 2
                            if estimated_tokens + msg_tokens > max_tokens:
                                break
                            messages.append({"role": item.role, "content": item.content})
                            seen_ids.add(item.id)
                            estimated_tokens += msg_tokens
                except Exception as e:
                    logger.warning(f"Semantic search failed: {e}")
            
            logger.info(f"Context optimized: {len(messages)} messages, ~{estimated_tokens} tokens (saved from {len(self.items)} total)")
            
            return messages
            
        except Exception as e:
            logger.error(f"get_context_messages error: {e}")
            # 返回空列表，让上层使用 recent_messages
            return []


# 全局向量存储字典，按 session_id 管理
_vector_stores: Dict[str, VectorMemoryStore] = {}


def get_vector_store(session_id: str) -> VectorMemoryStore:
    """Get or create vector store for a session"""
    if session_id not in _vector_stores:
        _vector_stores[session_id] = VectorMemoryStore()
    return _vector_stores[session_id]


def clear_vector_store(session_id: str):
    """Clear vector store for a session"""
    if session_id in _vector_stores:
        _vector_stores[session_id].clear()
        del _vector_stores[session_id]
