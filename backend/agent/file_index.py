"""
Workspace File Index - 文件内容向量索引
扫描 workspace 文件 → 提取摘要/chunk → BGE 嵌入 → FAISS 索引。
支持自然语言查询定位文件，如「那个配置文件」「数据库模型」等。
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 持久化索引目录
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FILE_INDEX_DIR = os.path.join(_BACKEND_ROOT, "data", "file_index")

# 索引配置
MAX_FILE_SIZE = 512 * 1024  # 512KB 以上跳过
CHUNK_SIZE = 500  # 每个 chunk 的字符数
CHUNK_OVERLAP = 100  # chunk 重叠
MAX_CHUNKS_PER_FILE = 10  # 每个文件最多索引的 chunk 数
HEAD_LINES = 30  # 默认摘要使用前 N 行

# 可索引的文件扩展名
INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".swift", ".kt", ".java",
    ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php",
    ".md", ".txt", ".rst", ".csv", ".yaml", ".yml", ".toml",
    ".json", ".xml", ".html", ".css", ".scss", ".less",
    ".sh", ".bash", ".zsh", ".fish",
    ".sql", ".r", ".lua", ".vim",
    ".env", ".gitignore", ".dockerignore",
    ".conf", ".cfg", ".ini", ".properties",
}

# 跳过的目录
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".env", "build", "dist", ".next", ".nuxt",
    "Pods", ".build", "DerivedData", "xcuserdata",
    ".DS_Store", "lib", "vendor",
}


@dataclass
class FileChunk:
    """文件的一个索引块"""
    file_path: str
    chunk_index: int  # 第几个 chunk（0=摘要）
    content: str  # chunk 内容
    line_start: int  # 起始行号
    line_end: int  # 结束行号


@dataclass
class IndexedFile:
    """已索引的文件元数据"""
    path: str
    rel_path: str  # 相对于 workspace 的路径
    size: int
    mtime: float
    content_hash: str
    chunk_count: int


class WorkspaceFileIndex:
    """
    工作区文件向量索引。

    流程：
    1. scan_workspace() → 扫描文件，得到 FileChunk 列表
    2. build_index() → 对 chunk 做 BGE 嵌入 + FAISS 索引
    3. search() → 自然语言查询 → 返回匹配的文件和片段
    """

    def __init__(self):
        self._workspace_root: str = ""
        self._indexed_files: Dict[str, IndexedFile] = {}  # rel_path -> IndexedFile
        self._chunks: List[FileChunk] = []
        self._embeddings: Optional[np.ndarray] = None
        self._faiss_index = None
        self._last_scan: float = 0

    @property
    def file_count(self) -> int:
        return len(self._indexed_files)

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def scan_workspace(self, root: str, force: bool = False) -> Dict[str, Any]:
        """
        扫描 workspace 目录，提取可索引的文件和摘要 chunk。

        Args:
            root: workspace 根目录绝对路径
            force: 强制全量重建（忽略 mtime 缓存）

        Returns:
            {"scanned": int, "indexed": int, "chunks": int, "skipped": int}
        """
        root = os.path.abspath(os.path.expanduser(root))
        self._workspace_root = root
        scanned = 0
        indexed = 0
        skipped = 0
        new_chunks: List[FileChunk] = []
        new_indexed: Dict[str, IndexedFile] = {}

        for dirpath, dirnames, filenames in os.walk(root):
            # 跳过排除目录
            dirnames[:] = [
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for fname in filenames:
                scanned += 1
                ext = os.path.splitext(fname)[1].lower()
                if ext not in INDEXABLE_EXTENSIONS and not fname.startswith("."):
                    skipped += 1
                    continue

                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, root)

                try:
                    stat = os.stat(fpath)
                except OSError:
                    skipped += 1
                    continue

                if stat.st_size > MAX_FILE_SIZE or stat.st_size == 0:
                    skipped += 1
                    continue

                # 增量：如果文件未变化，复用旧 chunk
                if not force and rel in self._indexed_files:
                    old = self._indexed_files[rel]
                    if old.mtime == stat.st_mtime and old.size == stat.st_size:
                        # 复用
                        new_indexed[rel] = old
                        for c in self._chunks:
                            if c.file_path == rel:
                                new_chunks.append(c)
                        indexed += 1
                        continue

                # 读取并生成 chunk
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError):
                    skipped += 1
                    continue

                if not content.strip():
                    skipped += 1
                    continue

                file_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
                chunks = self._extract_chunks(rel, content)
                new_chunks.extend(chunks)

                new_indexed[rel] = IndexedFile(
                    path=fpath,
                    rel_path=rel,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    content_hash=file_hash,
                    chunk_count=len(chunks),
                )
                indexed += 1

        self._indexed_files = new_indexed
        self._chunks = new_chunks
        self._embeddings = None
        self._faiss_index = None
        self._last_scan = time.time()

        logger.info(
            f"Workspace scan done: root={root}, scanned={scanned}, "
            f"indexed={indexed}, chunks={len(new_chunks)}, skipped={skipped}"
        )
        return {
            "scanned": scanned,
            "indexed": indexed,
            "chunks": len(new_chunks),
            "skipped": skipped,
        }

    def build_index(self) -> bool:
        """
        对所有 chunk 进行 BGE 嵌入，构建 FAISS 索引。
        需要先调用 scan_workspace()。

        Returns:
            是否成功
        """
        if not self._chunks:
            logger.warning("No chunks to index. Run scan_workspace first.")
            return False

        try:
            from .vector_store import get_embedding_model

            model = get_embedding_model()
            if model is None:
                logger.warning("Embedding model not available, file index disabled.")
                return False

            texts = [self._chunk_to_text(c) for c in self._chunks]

            # 分批编码，避免内存爆炸
            batch_size = 64
            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                embs = model.encode(
                    batch,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=batch_size,
                )
                all_embeddings.append(np.array(embs, dtype=np.float32))

            self._embeddings = np.vstack(all_embeddings)

            # 构建 FAISS 索引
            import faiss

            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)  # 内积（余弦相似度，已归一化）
            self._faiss_index.add(self._embeddings)

            logger.info(
                f"File index built: {len(self._chunks)} chunks, dim={dim}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to build file index: {e}")
            return False

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        自然语言查询文件。

        Args:
            query: 查询文本
            top_k: 返回最多 N 条结果
            min_score: 最低匹配分数

        Returns:
            [{"file": rel_path, "score": float, "chunk": str, "line_start": int, "line_end": int}, ...]
        """
        if self._faiss_index is None or not self._chunks:
            return []

        try:
            from .vector_store import get_embedding_model

            model = get_embedding_model()
            if model is None:
                return []

            q_emb = model.encode(
                query, normalize_embeddings=True, show_progress_bar=False
            )
            q_emb = np.array([q_emb], dtype=np.float32)

            scores, indices = self._faiss_index.search(q_emb, min(top_k * 2, len(self._chunks)))

            results = []
            seen_files = set()
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or score < min_score:
                    continue
                chunk = self._chunks[idx]
                # 同一文件只返回最佳 chunk
                if chunk.file_path in seen_files:
                    continue
                seen_files.add(chunk.file_path)
                results.append(
                    {
                        "file": chunk.file_path,
                        "score": round(float(score), 4),
                        "chunk": chunk.content[:200],
                        "line_start": chunk.line_start,
                        "line_end": chunk.line_end,
                    }
                )
                if len(results) >= top_k:
                    break

            return results
        except Exception as e:
            logger.error(f"File index search failed: {e}")
            return []

    def list_files(self) -> List[Dict[str, Any]]:
        """列出所有已索引文件的元数据"""
        return [
            {
                "path": f.rel_path,
                "size": f.size,
                "chunks": f.chunk_count,
            }
            for f in sorted(self._indexed_files.values(), key=lambda x: x.rel_path)
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "workspace_root": self._workspace_root,
            "file_count": len(self._indexed_files),
            "chunk_count": len(self._chunks),
            "index_ready": self._faiss_index is not None,
            "last_scan": self._last_scan,
        }

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _extract_chunks(self, rel_path: str, content: str) -> List[FileChunk]:
        """从文件内容中提取 chunk（摘要 + 分块）"""
        lines = content.split("\n")
        chunks = []

        # Chunk 0: 文件头摘要（前 HEAD_LINES 行）
        head = "\n".join(lines[:HEAD_LINES])
        if head.strip():
            chunks.append(
                FileChunk(
                    file_path=rel_path,
                    chunk_index=0,
                    content=head,
                    line_start=1,
                    line_end=min(HEAD_LINES, len(lines)),
                )
            )

        # 短文件不再分块
        if len(content) <= CHUNK_SIZE * 2:
            return chunks

        # 按字符数分块（带重叠）
        for i, start in enumerate(
            range(0, len(content), CHUNK_SIZE - CHUNK_OVERLAP)
        ):
            if i >= MAX_CHUNKS_PER_FILE:
                break
            end = min(start + CHUNK_SIZE, len(content))
            chunk_text = content[start:end]
            if not chunk_text.strip():
                continue

            # 估算行号
            line_s = content[:start].count("\n") + 1
            line_e = content[:end].count("\n") + 1

            chunks.append(
                FileChunk(
                    file_path=rel_path,
                    chunk_index=len(chunks),
                    content=chunk_text,
                    line_start=line_s,
                    line_end=line_e,
                )
            )

        return chunks

    @staticmethod
    def _chunk_to_text(chunk: FileChunk) -> str:
        """将 chunk 转为编码文本（加入文件路径前缀提高检索准确性）"""
        return f"File: {chunk.file_path}\n{chunk.content[:CHUNK_SIZE]}"


# ── 单例 ──────────────────────────────────────────────────────────────
_file_index: Optional[WorkspaceFileIndex] = None


def get_file_index() -> WorkspaceFileIndex:
    """获取全局 WorkspaceFileIndex 单例"""
    global _file_index
    if _file_index is None:
        _file_index = WorkspaceFileIndex()
    return _file_index
