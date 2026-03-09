#!/bin/bash
# ============================================================
# MaxAgent / Chow Duck — 一键完整安装脚本
# 适用于全新 macOS 环境，自动完成所有依赖安装
# 使用方式: bash install.sh
# 也可由 start.sh 在首次启动时自动调用（非交互模式）
# ============================================================

# 使用 set +e：允许单个步骤失败而不中断整体安装
set +e
cd "$(dirname "$0")"
BACKEND_ROOT="$(pwd)"

# 彩色输出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
section() { echo -e "\n${BLUE}══════ $* ══════${NC}"; }

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    MaxAgent / Chow Duck 安装程序      ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ──────────────────────────────────────────────
# 步骤 1: 检测并安装 Homebrew
# ──────────────────────────────────────────────
section "步骤 1/6: Homebrew"
if command -v brew >/dev/null 2>&1; then
    info "Homebrew 已安装: $(brew --version | head -1)"
else
    # 检查是否在交互式终端运行（tty=有则可提示，无则只警告）
    if [ -t 0 ]; then
        warn "Homebrew 未安装，正在安装（这是 macOS 包管理器，安装后续工具需要它）..."
        warn "安装过程中需要输入 macOS 密码（sudo），请按提示操作。"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # 确保 brew 在 PATH 中
        if [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f /usr/local/bin/brew ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        if command -v brew >/dev/null 2>&1; then
            info "Homebrew 安装成功！"
        else
            error "Homebrew 安装失败，请访问 https://brew.sh 手动安装后重新运行此脚本。"
        fi
    else
        warn "非交互模式：Homebrew 未安装，Node.js/cliclick 将跳过。"
        warn "请在终端运行: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        warn "安装 Homebrew 后重新启动应用，将自动完成剩余配置。"
    fi
fi

# 重新检查 brew（可能刚安装成功）
if command -v brew >/dev/null 2>&1; then
    BREW_AVAILABLE=true
else
    BREW_AVAILABLE=false
fi

# 确保 PATH 包含 Homebrew 路径
for _p in /opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin; do
    [[ ":$PATH:" != *":$_p:"* ]] && [ -d "$_p" ] && PATH="$_p:$PATH"
done
export PATH

# ──────────────────────────────────────────────
# 步骤 2: 检测并安装 Python 3.9+
# ──────────────────────────────────────────────
section "步骤 2/6: Python 3.9+"
_find_python() {
    for p in python3.12 python3.11 python3.10 python3.9; do
        if command -v "$p" >/dev/null 2>&1; then
            if "$p" -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
                echo "$p"; return 0
            fi
        fi
    done
    if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
        echo "python3"; return 0
    fi
    return 1
}

PY=$(_find_python || true)
if [ -z "$PY" ]; then
    if $BREW_AVAILABLE; then
        info "Python 3.9+ 未找到，正在通过 Homebrew 安装 Python 3.11..."
        brew install python@3.11 2>/dev/null && true
        PY=$(brew --prefix python@3.11 2>/dev/null)/bin/python3
    fi
    PY=$(_find_python || true)
    if [ -z "$PY" ]; then
        warn "Python 3.9+ 未安装，将尝试用系统 python3。"
        PY="python3"
    fi
fi
PY_VER=$($PY --version 2>&1 || echo 'unknown')
info "使用 Python: $PY_VER"

# ──────────────────────────────────────────────
# 步骤 3: 安装 Node.js（MCP 服务器需要 npx）
# ──────────────────────────────────────────────
section "步骤 3/6: Node.js / npx（MCP 服务器依赖）"
if command -v npx >/dev/null 2>&1; then
    info "Node.js 已安装: $(node --version), npx: $(npx --version)"
elif $BREW_AVAILABLE; then
    info "Node.js 未安装，正在通过 Homebrew 安装..."
    brew install node 2>&1 || warn "Node.js 安装失败，MCP stdio 服务器可能不可用"
    command -v node >/dev/null 2>&1 && info "Node.js 安装完成: $(node --version)" || warn "Node.js 安装异常"
else
    warn "Node.js 未安装且 Homebrew 不可用，MCP 服务器将不可用。"
fi

# ──────────────────────────────────────────────
# 步骤 4: 安装 cliclick（GUI 鼠标控制备用方案）
# ──────────────────────────────────────────────
section "步骤 4/6: cliclick（GUI 自动化）"
if command -v cliclick >/dev/null 2>&1; then
    info "cliclick 已安装: $(cliclick --version 2>/dev/null || echo 'ok')"
elif $BREW_AVAILABLE; then
    info "cliclick 未安装，正在通过 Homebrew 安装..."
    brew install cliclick 2>&1 || warn "cliclick 安装失败。"
    command -v cliclick >/dev/null 2>&1 && info "cliclick 安装完成。" || warn "cliclick 安装异常"
else
    warn "cliclick 未安装且 Homebrew 不可用，鼠标自动化将不可用。"
fi

# ──────────────────────────────────────────────
# 步骤 5: 创建 Python 虚拟环境 + 安装 Python 依赖
# ──────────────────────────────────────────────
section "步骤 5/6: Python 虚拟环境 + 依赖"
if [ -d "venv" ] && venv/bin/python -c "import fastapi, pyobjc" 2>/dev/null; then
    info "Python venv 已存在且依赖完整，跳过。"
else
    if [ -d "venv" ]; then
        info "检测到已有 venv，重新安装依赖..."
        source venv/bin/activate
    else
        info "创建 Python 虚拟环境..."
        "$PY" -m venv venv
        source venv/bin/activate
    fi
    PY_RUN="$VIRTUAL_ENV/bin/python"
    info "升级 pip..."
    "$PY_RUN" -m pip install --upgrade pip -q
    info "安装 Python 依赖（requirements.txt）..."
    "$PY_RUN" -m pip install -r requirements.txt
    info "Python 依赖安装完成。"
fi

# ──────────────────────────────────────────────
# 步骤 6: 配置检查和权限提示
# ──────────────────────────────────────────────
section "步骤 6/6: 配置检查"

# 检查 .env 文件
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn ".env 文件已从 .env.example 复制，请编辑填写 API Key。"
    else
        info "创建默认 .env 文件..."
        cat > .env << 'EOF'
# MaxAgent / Chow Duck 配置
# 必填: DeepSeek API Key
DEEPSEEK_API_KEY=

# 可选: GitHub Token（用于 MCP GitHub 工具，提高 API 速率限制）
# 获取地址: https://github.com/settings/tokens
GITHUB_TOKEN=

# 可选: 其他 LLM 配置
# OPENAI_API_KEY=
# OPENAI_BASE_URL=
EOF
        warn "已创建 .env 文件，请编辑填写 DEEPSEEK_API_KEY 等必要配置。"
    fi
else
    info ".env 文件已存在。"
fi

# 检查 API Key 是否配置
if [ -f ".env" ]; then
    if grep -q "DEEPSEEK_API_KEY=$" .env 2>/dev/null || ! grep -q "DEEPSEEK_API_KEY" .env 2>/dev/null; then
        warn "DEEPSEEK_API_KEY 未配置，Agent 将无法连接 AI 模型！"
        warn "请编辑 backend/.env 文件，填入你的 DeepSeek API Key。"
        warn "获取地址: https://platform.deepseek.com/api_keys"
    else
        info "DEEPSEEK_API_KEY 已配置 ✓"
    fi
fi

# macOS 辅助功能权限提示
echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  ⚠️  macOS 辅助功能权限（首次运行需手动授权）${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  为了让 Agent 能够控制鼠标和键盘，需要授予辅助功能权限："
echo "  1. 打开「系统设置」→「隐私与安全性」→「辅助功能」"
echo "  2. 找到终端（Terminal/iTerm）或应用程序，开启权限"
echo ""
echo "  如使用 Mac App，在首次运行时系统会自动弹出授权对话框。"
echo ""

# ──────────────────────────────────────────────
# 安装完成
# ──────────────────────────────────────────────
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              安装完成！                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "  启动后端服务："
echo "    bash start.sh"
echo ""
echo "  或者直接双击 Mac App 启动。"
echo ""

# 列出已安装内容汇总
echo "  已安装组件："
echo "    ✅ Python: $($PY --version 2>&1)"
echo "    ✅ Node.js: $(node --version 2>/dev/null || echo '已安装')"
echo "    ✅ npx: $(npx --version 2>/dev/null || echo '已安装')"
echo "    ✅ cliclick: $(command -v cliclick >/dev/null && echo '已安装' || echo '安装失败')"
echo "    ✅ Python venv: $([ -d venv ] && echo '已配置' || echo '未配置')"
echo ""
