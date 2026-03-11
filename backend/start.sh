#!/bin/bash
# Chow Duck Backend Startup Script
# 方案 C：启动时自动完成 Python/venv/依赖 安装，避免冲突与多情况覆盖

set -e
cd "$(dirname "$0")"
BACKEND_ROOT="$(pwd)"

# 确保 PATH 包含 Homebrew 和常用工具路径（从 App 启动时 PATH 可能非常有限）
# 包括 Homebrew 通过 keg-only 方式安装的 Node.js（如 node@22）
_EXTRA_PATHS="/opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin /usr/local/sbin"
# 自动发现 Homebrew keg-only Node.js（如 /opt/homebrew/opt/node@22/bin）
for _node_keg in /opt/homebrew/opt/node@*/bin /usr/local/opt/node@*/bin; do
    [ -d "$_node_keg" ] && _EXTRA_PATHS="$_EXTRA_PATHS $_node_keg"
done
for _extra_path in $_EXTRA_PATHS; do
    case ":$PATH:" in
        *":$_extra_path:"*) ;;
        *) [ -d "$_extra_path" ] && PATH="$_extra_path:$PATH" ;;
    esac
done
export PATH

# ──────────────────────────────────────────────
# 首次运行检测：自动调用 install.sh 完成全量依赖安装
# - 有 Homebrew → 全程非交互，自动安装 Node.js / cliclick / venv / .env
# - 无 Homebrew → 提示用户手动运行一次 install.sh
# 安装完成后创建 .backend_setup_done 标记，后续启动跳过此流程
# ──────────────────────────────────────────────
SETUP_MARKER="$BACKEND_ROOT/.backend_setup_done"
if [ ! -f "$SETUP_MARKER" ]; then
    echo "[INFO] 检测到首次启动，开始自动安装依赖..."
    if command -v brew >/dev/null 2>&1; then
        # Homebrew 可用：install.sh 完全非交互，自动完成
        echo "[INFO] 正在运行一键安装脚本（首次运行约需 3-10 分钟，仅此一次）..."
        if bash "$BACKEND_ROOT/install.sh"; then
            echo "$$ $(date)" > "$SETUP_MARKER"
            echo "[INFO] 首次安装完成，后续启动将直接跳过此步骤。"
        else
            echo "[WARN] install.sh 执行中出现警告，将继续尝试启动..."
        fi
    else
        # 无 Homebrew：无法非交互安装，提示用户手动运行
        echo ""
        echo "[SETUP REQUIRED] ════════════════════════════════════════"
        echo "[SETUP REQUIRED]  首次使用需完成一次性环境安装："
        echo "[SETUP REQUIRED]  1. 打开终端 (Terminal)"
        echo "[SETUP REQUIRED]  2. 运行: bash '$BACKEND_ROOT/install.sh'"
        echo "[SETUP REQUIRED]  3. 安装完成后重新启动应用"
        echo "[SETUP REQUIRED] ════════════════════════════════════════"
        echo ""
        echo "[WARN] 将尝试以当前环境启动，部分功能（MCP/GUI控制）可能不可用。"
    fi
fi

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

# 首次运行：自动创建 .env 配置文件（避免用户不知道需要配置）
_ENV_TARGET=""
if [ -n "$MACAGENT_DATA_DIR" ]; then
    mkdir -p "$MACAGENT_DATA_DIR"
    _ENV_TARGET="$MACAGENT_DATA_DIR/.env"
else
    _ENV_TARGET="$BACKEND_ROOT/.env"
fi
if [ ! -f "$_ENV_TARGET" ]; then
    echo "[INFO] 首次运行：自动创建配置文件 $_ENV_TARGET"
    cat > "$_ENV_TARGET" << 'EOF'
# MaxAgent / Chow Duck 配置
# 必填: AI 模型 API Key（至少填一个）
DEEPSEEK_API_KEY=

# 可选: GitHub Token（用于 MCP GitHub 工具）
# 获取地址: https://github.com/settings/tokens
GITHUB_TOKEN=

# 可选: 其他 LLM
# OPENAI_API_KEY=
# OPENAI_BASE_URL=
# ANTHROPIC_API_KEY=
EOF
    echo "[INFO] 请在应用设置页面填写 DEEPSEEK_API_KEY 等 API Key，或直接编辑: $_ENV_TARGET"
fi

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

# 优先使用 venv（环境完整、版本可控），其次 lib/
USE_LIB=0

# Helper: install dependencies into the currently activated venv.
# If pip is missing inside the venv (e.g., venv created with --without-pip),
# bootstrap it first with ensurepip.  Returns 0 on success.
_venv_install_deps() {
    local py_run="$1"
    # Ensure pip exists in the venv (not system pip)
    if ! "$py_run" -m pip --version 2>/dev/null; then
        "$py_run" -m ensurepip --upgrade 2>/dev/null || {
            echo "[WARN] ensurepip failed — venv may be broken"
            return 1
        }
    fi
    "$py_run" -m pip install --quiet --upgrade pip 2>/dev/null || true
    "$py_run" -m pip install --quiet -r requirements.txt || return 1
    if [ "$ENABLE_VECTOR_SEARCH" = "true" ]; then
        "$py_run" -m pip install --quiet sentence-transformers faiss-cpu numpy 2>/dev/null || true
    fi
    return 0
}

# Helper: delete and recreate venv from scratch, then install deps.
_recreate_venv() {
    echo "[INFO] Recreating venv from scratch using $PY ..."
    deactivate 2>/dev/null || true
    rm -rf venv
    "$PY" -m venv venv
    source venv/bin/activate
    PY_RUN="$VIRTUAL_ENV/bin/python"
    [ -x "$PY_RUN" ] || PY_RUN="$VIRTUAL_ENV/bin/python3"
    _venv_install_deps "$PY_RUN"
}

if [ -d "venv" ] && [ -x "venv/bin/python" ]; then
    # venv 的 python 可能是软链接指向系统 python；验证存在且可执行
    if "venv/bin/python" -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
        source venv/bin/activate
        # Use explicit VIRTUAL_ENV path — immune to PATH / externally-managed-environment issues
        PY_RUN="$VIRTUAL_ENV/bin/python"
        [ -x "$PY_RUN" ] || PY_RUN="$VIRTUAL_ENV/bin/python3"
        # 依赖健康检查：venv 存在但核心包缺失时自动重装，避免损坏/不完整
        if ! $PY_RUN -c "import fastapi" 2>/dev/null; then
            echo "[INFO] venv incomplete, reinstalling dependencies..."
            if ! _venv_install_deps "$PY_RUN"; then
                echo "[INFO] Install failed (possibly broken venv), recreating..."
                _recreate_venv
            fi
        fi
        USE_LIB=0
        echo "[INFO] Using venv Python: $PY_RUN ($($PY_RUN --version 2>&1))"
    fi
fi
# 回退到打包时预装的 lib（无需 pip install，需 Python 版本匹配）
if [ "$USE_LIB" = "0" ] && [ -z "$VIRTUAL_ENV" ]; then
    if [ -d "lib" ] && [ -f "lib/.installed" ]; then
        if [ -f "lib/.python_version" ]; then
            NEED_VER=$(cat lib/.python_version)
            CUR_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            if [ "$CUR_VER" = "$NEED_VER" ]; then
                export PYTHONPATH="$(pwd)/lib:$PYTHONPATH"
                PY_RUN="$PY"
                USE_LIB=1
                echo "[INFO] Using lib/ with $PY (version $CUR_VER)"
            fi
        fi
    fi
fi
if [ "$USE_LIB" = "0" ] && [ -z "$VIRTUAL_ENV" ]; then
    if [ -d "venv" ]; then
        # venv exists but Python check above may have failed (broken symlinks) — recreate
        echo "[INFO] venv exists but may be broken, recreating..."
        _recreate_venv
    else
        echo "[INFO] Creating virtual environment and installing dependencies..."
        "$PY" -m venv venv
        source venv/bin/activate
        PY_RUN="$VIRTUAL_ENV/bin/python"
        [ -x "$PY_RUN" ] || PY_RUN="$VIRTUAL_ENV/bin/python3"
        _venv_install_deps "$PY_RUN"
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

# RapidOCR 按需安装（GUI 视觉识别管道，~50MB，首次约 30 秒）
# 优先使用 rapidocr-onnxruntime（兼容 Python 3.14+），回退 PaddleOCR
ENABLE_PADDLE_OCR="${ENABLE_PADDLE_OCR:-true}"
if [ "$ENABLE_PADDLE_OCR" = "true" ]; then
    if ! $PY_RUN -c "import rapidocr_onnxruntime" 2>/dev/null && ! $PY_RUN -c "import paddleocr" 2>/dev/null; then
        echo "[INFO] Installing RapidOCR (ONNX) for GUI vision pipeline (~50MB, one-time)..."
        "$PY_RUN" -m pip install --quiet rapidocr-onnxruntime 2>/dev/null && \
            echo "[INFO] RapidOCR installed successfully." || \
            echo "[WARN] RapidOCR install failed, vision OCR fallback will not be available."
    fi
else
    echo "[INFO] ENABLE_PADDLE_OCR=false: OCR disabled. Add ENABLE_PADDLE_OCR=true to .env for vision OCR."
fi

# 自动安装 cliclick（GUI 自动化鼠标控制依赖）
if ! command -v cliclick >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "[INFO] cliclick not found, installing via Homebrew (GUI automation support)..."
        brew install cliclick 2>/dev/null && echo "[INFO] cliclick installed successfully." || echo "[WARN] cliclick install failed, mouse automation may not work."
    else
        echo "[WARN] cliclick not found and Homebrew not available. Mouse automation will not work. Install manually: brew install cliclick"
    fi
fi


# 自动安装 Node.js（MCP stdio 服务器依赖 npx/node）
if ! command -v npx >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "[INFO] npx/Node.js not found, installing via Homebrew (MCP server support)..."
        brew install node 2>/dev/null && echo "[INFO] Node.js installed successfully." || echo "[WARN] Node.js install failed, MCP stdio servers may not work."
        # 重新刷新 PATH（Homebrew 新安装的 Node 可能还未加入当前 shell PATH）
        for _node_keg in /opt/homebrew/opt/node@*/bin /opt/homebrew/bin; do
            [ -d "$_node_keg" ] && PATH="$_node_keg:$PATH"
        done
        export PATH
    else
        echo "[WARN] npx not found and Homebrew not available. MCP stdio servers will not work. Install Node.js manually."
    fi
fi
# 立即输出日志，便于确认启动进度（避免“卡住”的错觉）
export PYTHONUNBUFFERED=1

# Duck 模式下使用 DUCK_PORT，普通模式读取端口配置
if [ "${DUCK_MODE:-0}" = "1" ]; then
    PORT="${DUCK_PORT:-8766}"
    echo "[Duck] Duck mode enabled, using port $PORT"
else
    # 从 macagent_ports.json 读取端口配置（Mac App 写入）
    PORTS_FILE="${TMPDIR:-/tmp}/macagent_ports.json"
    if [ -f "$PORTS_FILE" ] && command -v python3 >/dev/null 2>&1; then
        PORT=$(python3 -c "import json; print(json.load(open('$PORTS_FILE')).get('backend_port', 8765))" 2>/dev/null || echo 8765)
    else
        PORT=8765
    fi
    # 启动前释放 8765 端口，避免 Address already in use
    if lsof -ti:$PORT >/dev/null 2>&1; then
        echo "Port $PORT in use, stopping existing process..."
        lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
fi
export DUCK_PORT="$PORT"

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
