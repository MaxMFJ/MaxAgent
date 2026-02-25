#!/usr/bin/env python3
"""
检测 Ollama 是否已启动并可用的脚本
用法: python scripts/check_ollama.py
"""
import json
import sys
import urllib.request

URL = "http://localhost:11434/api/tags"


def check_ollama() -> bool:
    try:
        req = urllib.request.urlopen(URL, timeout=5)
        data = json.loads(req.read())
        models = data.get("models", [])
        if not models:
            print("⚠️ Ollama 已运行，但未拉取任何模型")
            print("   运行: ollama pull qwen2.5:3b")
            return False
        names = [m.get("name", "") for m in models]
        print(f"✅ Ollama 已启动，可用模型: {', '.join(names)}")
        return True
    except OSError as e:
        print("❌ 无法连接 localhost:11434，请确认 Ollama 已启动")
        return False
    except Exception as e:
        print(f"❌ 检测失败: {e}")
        return False


if __name__ == "__main__":
    ok = check_ollama()
    sys.exit(0 if ok else 1)
