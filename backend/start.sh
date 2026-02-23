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

echo "Starting MacAgent backend..."
echo "Note: First run will download the BGE embedding model (~1.5GB), please wait..."
python main.py
