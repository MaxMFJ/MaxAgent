#!/bin/bash
# Chow Duck Backend Startup Script
# 方案 C：启动时自动完成 Python/venv/依赖 安装，避免冲突与多情况覆盖

set -e
cd "$(dirname "$0")"
BACKEND_ROOT="$(pwd)"

# 单实例锁：同一 backend 目录只允许一个后端进程，避免重复启动冲突
START_LOCK="$BACKEND_ROOT/.start.lock"
START_LOCK_FD=200
try_acquire_lock() {
    if [ -f "$START_LOCK" ]; then
        OLD_PID=$(cat "$START_LOCK" 2>/dev/null)
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            echo "[WARN] Backend already running (PID $OLD_PID). Stop it first or use another backend copy."
            exit 2
        fi
        rm -f "$START_LOCK"
    fi
    echo $$ > "$START_LOCK"
}
release_lock() { rm -f "$START_LOCK"; }
trap release_lock EXIT
try_acquire_lock

# 加载 .env（优先 MACAGENT_DATA_DIR，便于应用内配置）
if [ -n "$MACAGENT_DATA_DIR" ] && [ -f "$MACAGENT_DATA_DIR/.env" ]; then
    export $(grep -v '^#' "$MACAGENT_DATA_DIR/.env" | xargs)
fi
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
# 打包版本默认关闭 RAG（~600MB），用户启用时首次自动安装
if [ -f .packaged ]; then
    ENABLE_VECTOR_SEARCH="${ENABLE_VECTOR_SEARCH:-false}"
else
    ENABLE_VECTOR_SEARCH="${ENABLE_VECTOR_SEARCH:-true}"
fi

# Python 版本检查与自动安装（方案 C：尽量自动化）
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY="python"
_find_python() {
    for p in python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$p" >/dev/null 2>&1; then
            if "$p" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
                echo "$p"
                return 0
            fi
        fi
    done
    if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        echo "python3"
        return 0
    fi
    if command -v python >/dev/null 2>&1 && python -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        echo "python"
        return 0
    fi
    echo ""
    return 1
}
if ! command -v "$PY" >/dev/null 2>&1; then
    PY=""
fi
if [ -z "$PY" ] || ! "$PY" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    PY=$(_find_python)
fi
if [ -z "$PY" ]; then
    if command -v brew >/dev/null 2>&1; then
        echo "[INFO] Python 3.8+ not found. Trying: brew install python@3.10 ..."
        brew install python@3.10 2>/dev/null || true
        for p in python3.10 "$(brew --prefix python@3.10 2>/dev/null)/bin/python3"; do
            [ -z "$p" ] && continue
            if [ -x "$p" ] 2>/dev/null && "$p" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
                PY="$p"
                break
            fi
        done
    fi
fi
if [ -z "$PY" ] || ! "$PY" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
    echo "[ERROR] Python 3.8+ required. Install: brew install python@3.10  (or install from python.org)"
    exit 1
fi
MAJOR=$("$PY" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
MINOR=$("$PY" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)

# 优先使用打包时预装的 lib（无需 pip install，需 Python 版本匹配）
USE_LIB=0
if [ -d "lib" ] && [ -f "lib/.installed" ]; then
    if [ -f "lib/.python_version" ]; then
        NEED_VER=$(cat lib/.python_version)
        CUR_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        if [ "$CUR_VER" = "$NEED_VER" ]; then
            export PYTHONPATH="$(pwd)/lib:$PYTHONPATH"
            PY_RUN="$PY"
            USE_LIB=1
        fi
    fi
fi
if [ "$USE_LIB" = "0" ]; then
    if [ -d "venv" ]; then
        source venv/bin/activate
        PY_RUN="python"
        # 依赖健康检查：venv 存在但核心包缺失时自动重装，避免损坏/不完整
        if ! $PY_RUN -c "import fastapi" 2>/dev/null; then
            echo "[INFO] venv incomplete, reinstalling dependencies..."
            "$PY_RUN" -m pip install --quiet --upgrade pip 2>/dev/null || true
            "$PY_RUN" -m pip install --quiet -r requirements.txt
            if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
                "$PY_RUN" -m pip install --quiet sentence-transformers faiss-cpu numpy 2>/dev/null || true
            fi
        fi
    else
        echo "[INFO] Creating virtual environment and installing dependencies..."
        "$PY" -m venv venv
        source venv/bin/activate
        "$PY_RUN" -m pip install --quiet --upgrade pip 2>/dev/null || true
        "$PY_RUN" -m pip install --quiet -r requirements.txt
        if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
            "$PY_RUN" -m pip install --quiet sentence-transformers faiss-cpu numpy 2>/dev/null || true
        fi
        PY_RUN="python"
    fi
fi

# 启用向量搜索时：若未安装则自动安装到 Application Support（0 操作）
RAG_LIB="$HOME/Library/Application Support/com.macagent.app/backend_rag_lib"
if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
    if ! $PY_RUN -c "import sentence_transformers" 2>/dev/null; then
        echo "[INFO] Installing RAG dependencies (sentence-transformers, ~3–5 min, one-time)..."
        mkdir -p "$RAG_LIB"
        "$PY" -m pip install --quiet --target "$RAG_LIB" sentence-transformers faiss-cpu numpy
        echo "[INFO] RAG dependencies installed"
    fi
    [ -d "$RAG_LIB" ] && export PYTHONPATH="$RAG_LIB:$PYTHONPATH"
elif [ "$ENABLE_VECTOR_SEARCH" != "true" ]; then
    echo "[INFO] ENABLE_VECTOR_SEARCH=false: RAG disabled. Add ENABLE_VECTOR_SEARCH=true to .env for semantic search."
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
exec $PY_RUN main.py
