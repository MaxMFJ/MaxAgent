#!/usr/bin/env python3
"""
测试本地模型对自主任务的实际输出，排查解析失败原因
仅使用标准库，无需安装额外依赖
"""
import json
import re
import urllib.request

SYSTEM_PROMPT = """你是一个完全自主执行的 macOS Agent。你会自动完成用户的任务，无需用户干预。

## 输出格式
你必须始终以 JSON 格式输出下一步动作：
```json
{
  "reasoning": "解释为什么执行这个动作",
  "action_type": "动作类型",
  "params": { ... }
}
```

## 可用的动作类型

1. **open_app** - 打开应用程序
   {"action_type": "open_app", "params": {"app_name": "Safari"}, "reasoning": "..."}

2. **finish** - 完成任务
   {"action_type": "finish", "params": {"summary": "任务完成总结", "success": true}, "reasoning": "任务已完成"}

现在，根据用户的任务，输出下一步动作的 JSON。"""


def call_ollama(task: str) -> str:
    payload = json.dumps({
        "model": "qwen2.5:3b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"任务: {task}\n\n开始执行任务。请分析任务并输出第一步动作的 JSON。"},
        ],
        "stream": False,
        "temperature": 0.3,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data.get("message", {}).get("content", "")


def extract_json_candidates(text):
    out = []
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                out.append(text[start : i + 1])
                start = -1
    return out


def try_parse_action(text):
    if not text:
        return None

    # Step 1: extract ```json ... ```
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if m:
        block = m.group(1).strip()
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("action_type"):
                return data
        except json.JSONDecodeError:
            pass

    # Step 2: extract { ... } blocks
    for candidate in extract_json_candidates(text):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data.get("action_type"):
                return data
        except json.JSONDecodeError:
            pass

    # Step 3: whole text
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict) and data.get("action_type"):
            return data
    except json.JSONDecodeError:
        pass

    return None


if __name__ == "__main__":
    task = "打开微信"
    print(f"=== 测试任务: {task} ===\n")

    print("调用 Ollama (qwen2.5:3b)...")
    content = call_ollama(task)

    print(f"\n=== 原始输出 ({len(content)} 字符) ===")
    print(repr(content))
    print()
    print(content)

    print("\n=== 解析测试 ===")
    result = try_parse_action(content)
    if result:
        print(f"✅ 解析成功: action_type={result.get('action_type')}, params={result.get('params')}")
    else:
        print("❌ 解析失败")

        # 详细排查
        print("\n--- code block ---")
        m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", content)
        if m:
            print(f"找到: {repr(m.group(1).strip()[:300])}")
        else:
            print("未找到 ```json...``` block")

        print("\n--- JSON candidates ---")
        for i, c in enumerate(extract_json_candidates(content)):
            print(f"  [{i}] {repr(c[:300])}")
            try:
                d = json.loads(c)
                print(f"       -> 解析成功: {d}")
            except json.JSONDecodeError as e:
                print(f"       -> 解析失败: {e}")

        if not extract_json_candidates(content):
            print("  未找到任何 { ... } 块")
