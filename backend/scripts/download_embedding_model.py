#!/usr/bin/env python3
"""
一次性将 BGE 嵌入模型下载到项目内 backend/models/embedding/，之后启动将从此目录加载，不再访问 Hugging Face。
用法: cd backend && python3 scripts/download_embedding_model.py
可选: EMBEDDING_MODEL=BAAI/bge-base-zh-v1.5 python3 scripts/download_embedding_model.py
"""

import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _backend_dir)
os.chdir(_backend_dir)

# 与 vector_store 使用相同路径
LOCAL_EMBEDDING_DIR = os.path.join(_backend_dir, "models", "embedding")
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def main():
    model_name = os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    short_name = model_name.split("/")[-1] if "/" in model_name else model_name
    save_path = os.path.join(LOCAL_EMBEDDING_DIR, short_name)

    if os.path.isfile(os.path.join(save_path, "config.json")):
        print(f"模型已存在: {save_path}，跳过下载。")
        print("若需重新下载请先删除该目录。")
        return 0

    os.makedirs(LOCAL_EMBEDDING_DIR, exist_ok=True)
    print(f"正在从 Hugging Face 下载 {model_name} 到 {save_path} ...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        model.save(save_path)
        print(f"已保存到 {save_path}。之后启动将从此目录加载，无需再联网。")
        return 0
    except Exception as e:
        print(f"下载失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
