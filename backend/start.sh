#!/bin/bash
# Chow Duck Backend Startup Script

cd "$(dirname "$0")"

# 加载 .env 中的 ENABLE_VECTOR_SEARCH（若有）
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
ENABLE_VECTOR_SEARCH="${ENABLE_VECTOR_SEARCH:-true}"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 仅在启用向量搜索时安装/检查 BGE 依赖（否则跳过，加快启动）
if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
    if ! python -c "import sentence_transformers" 2>/dev/null; then
        echo "[INFO] Installing embedding dependencies (sentence-transformers, ~2–5 min on first run)..."
        pip install sentence-transformers faiss-cpu numpy
    fi
else
    echo "[INFO] ENABLE_VECTOR_SEARCH=false: skipping BGE embedding (RAG disabled)."
fi

# 立即输出日志，便于确认启动进度（避免“卡住”的错觉）
export PYTHONUNBUFFERED=1

# 启动前释放 8765 端口，避免 Address already in use
PORT=8765
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "Port $PORT in use, stopping existing process..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo "Starting Chow Duck backend..."
if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
    # 已下载到本地时不再提示“下载”，只提示后台加载
    if [ -d "models/embedding" ] && ls models/embedding/*/config.json 1>/dev/null 2>&1; then
        echo "Note: BGE uses local cache, loading in background. Server ready when you see 'Uvicorn running'."
    else
        echo "Note: BGE embedding loads in background (default ~90MB). Server ready when you see 'Uvicorn running'."
    fi
else
    echo "Note: Vector search disabled. Enable with ENABLE_VECTOR_SEARCH=true in .env for RAG."
fi
exec python main.py
