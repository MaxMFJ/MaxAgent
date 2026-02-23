#!/bin/bash
# MacAgent Backend Startup Script

cd "$(dirname "$0")"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# 检查向量搜索依赖是否已安装
if ! python -c "import sentence_transformers" 2>/dev/null; then
    echo "Installing embedding dependencies (this may take a while on first run)..."
    pip install sentence-transformers faiss-cpu numpy
fi

# 启动前释放 8765 端口，避免 Address already in use
PORT=8765
if lsof -ti:$PORT >/dev/null 2>&1; then
    echo "Port $PORT in use, stopping existing process..."
    lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo "Starting MacAgent backend..."
echo "Note: First run will download the BGE embedding model (~1.5GB), please wait..."
python main.py
