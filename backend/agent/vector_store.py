"""
Vector Store for Semantic Context Management
Uses BGE embedding models for efficient context retrieval
"""

import os
import logging
import threading
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)
_model_lock = threading.Lock()

# 配置（默认 bge-small ~90MB；bge-m3 约 1.5GB）
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
ENABLE_VECTOR_SEARCH = os.getenv("ENABLE_VECTOR_SEARCH", "true").lower() == "true"
# 国内可设 HF_ENDPOINT=https://hf-mirror.com 加速下载
# 关闭 BGE/sentence_transformers 的 tqdm 进度条，避免被日志/前端误显示为 [ERROR]
os.environ["TQDM_DISABLE"] = "1"

# 项目内嵌模型目录：若存在则优先从此加载，不再启动时从 Hugging Face 下载
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCAL_EMBEDDING_DIR = os.path.join(_BACKEND_ROOT, "models", "embedding")

# 延迟加载，避免启动时间过长
_embedding_model = None
_model_loading = False


def _get_local_embedding_path() -> Optional[str]:
    """
    若项目内已存在嵌入模型目录则返回其路径，用于离线/内嵌加载。
    目录名与 EMBEDDING_MODEL 对应：BAAI/bge-small-zh-v1.5 -> bge-small-zh-v1.5
    """
    if not os.path.isdir(LOCAL_EMBEDDING_DIR):
        return None
    # 使用模型短名作为子目录（如 bge-small-zh-v1.5）
    short_name = EMBEDDING_MODEL.split("/")[-1] if "/" in EMBEDDING_MODEL else EMBEDDING_MODEL
    local_path = os.path.join(LOCAL_EMBEDDING_DIR, short_name)
    if not os.path.isdir(local_path):
        return None
    config_path = os.path.join(local_path, "config.json")
    if not os.path.isfile(config_path):
        return None
    return local_path


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
    """懒加载嵌入模型（线程安全）"""
    global _embedding_model, _model_loading

    if not ENABLE_VECTOR_SEARCH:
        return None

    if _embedding_model is not None:
        return _embedding_model

    if _model_loading:
        logger.debug("Model is loading, skipping embedding")
        return None

    with _model_lock:
        if _embedding_model is not None:
            return _embedding_model
        _model_loading = True
        try:
            from sentence_transformers import SentenceTransformer

            device = _get_embedding_device()
            local_path = _get_local_embedding_path()

            if local_path:
                # 优先从项目内 models/embedding 加载，不访问网络
                logger.info(f"Loading embedding model from local: {local_path} on {device}...")
                _embedding_model = SentenceTransformer(local_path, device=device, local_files_only=True)
                logger.info(f"Embedding model loaded (local): {local_path}, dim={_embedding_model.get_sentence_embedding_dimension()}")
            else:
                # 回退：从 Hugging Face 下载（需网络，可能受 HF 限速影响）
                model_name = EMBEDDING_MODEL
                logger.info(f"Loading embedding model: {model_name} on {device}...")
                # 模型选项：
                # - BAAI/bge-m3: 最强，支持多语言，但较大 (~1.5GB)
                # - BAAI/bge-large-zh-v1.5: 中文优秀 (~1.3GB)
                # - BAAI/bge-small-zh-v1.5: 中文，小而快 (~90MB) [默认]
                # - BAAI/bge-base-zh-v1.5: 中文，平衡选择 (~400MB)
                # Apple Silicon 上使用 device='cpu' 以避免 MPS SDPA 崩溃
                _embedding_model = SentenceTransformer(model_name, device=device)
                logger.info(f"Embedding model loaded: {model_name}, dim={_embedding_model.get_sentence_embedding_dimension()}")
        except Exception as e:
            logger.warning(f"Failed to load embedding model {EMBEDDING_MODEL}: {e}")
            try:
                from sentence_transformers import SentenceTransformer
                device = _get_embedding_device()
                fallback_local = os.path.join(LOCAL_EMBEDDING_DIR, "bge-small-zh-v1.5")
                if os.path.isdir(fallback_local) and os.path.isfile(os.path.join(fallback_local, "config.json")):
                    _embedding_model = SentenceTransformer(fallback_local, device=device, local_files_only=True)
                    logger.info(f"Loaded fallback model (local): {fallback_local}")
                else:
                    _embedding_model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device=device)
                    logger.info("Loaded fallback model: bge-small-zh-v1.5 from HF")
            except Exception as e2:
                logger.error(f"Failed to load any embedding model: {e2}")
                _embedding_model = None
        finally:
            _model_loading = False
    
    return _embedding_model


def _force_reload_embedding_model():
    """强制重新加载嵌入模型（用于 Broken pipe 恢复）"""
    global _embedding_model, _model_loading
    logger.info("Force-reloading embedding model...")
    _embedding_model = None
    _model_loading = False
    get_embedding_model()


def preload_embedding_model():
    """后台预加载 BGE 模型，不阻塞启动；RAG 可用时日志会打印 'Embedding model loaded'"""
    import threading
    def _load():
        try:
            get_embedding_model()
        except Exception as e:
            logger.warning(f"Background BGE load failed: {e}. RAG/vector search disabled.")
    thread = threading.Thread(target=_load, daemon=True)
    thread.start()
    logger.info("BGE embedding loading in background (see 'Embedding model loaded' when RAG is ready)")


def encode_text_for_similarity(text: str):
    """
    v3.1: 对单段文本编码为归一化向量，供 escalation 等相似度比较。
    返回 np.ndarray 或 None（模型不可用时）。
    """
    model = get_embedding_model()
    if model is None or not text:
        return None
    try:
        import numpy as np
        emb = model.encode(text.strip()[:1000], normalize_embeddings=True, show_progress_bar=False)
        return np.array(emb, dtype=np.float32)
    except Exception as e:
        logger.debug("encode_text_for_similarity failed: %s", e)
        return None


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
    
    def _compute_embedding(self, text: str, _retry: bool = True) -> Optional[np.ndarray]:
        """Compute embedding for text. Retries once on Broken pipe by reloading the model."""
        model = get_embedding_model()
        if model is None:
            return None

        try:
            embedding = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
            return np.array(embedding, dtype=np.float32)
        except BrokenPipeError:
            if _retry:
                logger.warning("Broken pipe in embedding, reloading model and retrying...")
                _force_reload_embedding_model()
                return self._compute_embedding(text, _retry=False)
            logger.error("Broken pipe persists after model reload")
            return None
        except Exception as e:
            if "Broken pipe" in str(e) and _retry:
                logger.warning("Broken pipe in embedding, reloading model and retrying...")
                _force_reload_embedding_model()
                return self._compute_embedding(text, _retry=False)
            logger.error(f"Failed to compute embedding: {e}")
            try:
                from .system_message_service import get_system_message_service, MessageCategory
                get_system_message_service().add_error(
                    "向量嵌入失败",
                    str(e),
                    source="vector_store",
                    category=MessageCategory.SYSTEM_ERROR.value,
                )
            except Exception as _e:
                logger.debug(f"Failed to push embedding error notification: {_e}")
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
        recent_count: int = 4,
        semantic_count: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get optimized context messages for LLM.
        Combines recent messages (连贯性) with semantically relevant ones (相关性).
        每条消息内容超过 max_msg_chars 时会被截断，避免单条消息消耗过多 token。

        **重要**: 采用 newest-first 策略：先保证最新消息（当前用户查询）必定入选，
        剩余预算按时间从新到旧填充历史，防止旧消息挤占预算导致当前查询被丢弃。
        """
        MAX_MSG_CHARS = 800  # 单条消息最大字符数

        def _truncate(text: str) -> str:
            if len(text) <= MAX_MSG_CHARS:
                return text
            return text[:MAX_MSG_CHARS] + "...[截断]"

        def _estimate_tokens(text: str) -> int:
            # 中文约 1.5 字符/token，英文约 4 字符/token，取中间值 ~2
            return len(text) // 2

        try:
            collected = []  # (item, content) 按 newest-first 暂存
            seen_ids = set()
            estimated_tokens = 0

            # 1. 最近消息：newest-first，确保当前用户查询永远不被丢弃
            recent = self.get_recent(recent_count)  # newest first
            for item in recent:
                if item.id not in seen_ids:
                    content = _truncate(item.content)
                    msg_tokens = _estimate_tokens(content)
                    if estimated_tokens + msg_tokens > max_tokens:
                        break
                    collected.append({"role": item.role, "content": content})
                    seen_ids.add(item.id)
                    estimated_tokens += msg_tokens

            # 2. 语义相关的历史消息（BGE 检索，补充与当前查询相关的上下文）
            semantic_msgs = []
            if current_query:
                try:
                    relevant = self.search(current_query, top_k=semantic_count)
                    for item in relevant:
                        if item.id not in seen_ids:
                            content = _truncate(item.content)
                            msg_tokens = _estimate_tokens(content)
                            if estimated_tokens + msg_tokens > max_tokens:
                                break
                            semantic_msgs.append({"role": item.role, "content": content})
                            seen_ids.add(item.id)
                            estimated_tokens += msg_tokens
                except Exception as e:
                    logger.warning(f"Semantic search failed: {e}")

            # 3. 组装最终消息列表：语义历史在前（较旧），最近消息在后（较新），保持时间顺序
            #    collected 是 newest-first，需要反转为 chronological 顺序
            messages = semantic_msgs + list(reversed(collected))

            logger.info(
                f"Context optimized: {len(messages)} msgs, ~{estimated_tokens} tokens "
                f"(from {len(self.items)} total items, recent={recent_count}, semantic={semantic_count})"
            )

            return messages

        except Exception as e:
            logger.error(f"get_context_messages error: {e}")
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
