#!/usr/bin/env python3
"""
MacAgent v3.2 内部 Benchmark 自动化脚本
========================================

使用方式：
  cd backend
  python scripts/run_benchmark.py [--url http://localhost:8000] [--cases B1,B2,B7] [--out ./data/benchmark]

原理：
  1. 依次通过 WebSocket 发送内部 benchmark 用例
  2. 等待 task_complete 消息或超时
  3. 汇总每个用例的结果（通过/失败、步数、token 数、延迟）
  4. 将汇总结果写入 data/benchmark/results_{timestamp}.json

用例来源：
  - docs/内部benchmark用例集.md 定义的 B1~B7
  - 可通过 --cases 指定子集
"""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保 backend 可 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import websockets  # type: ignore
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

# ──────────────────────────────────────────────────────────────────────────────
# 内置用例（与 docs/内部benchmark用例集.md 对齐）
# ──────────────────────────────────────────────────────────────────────────────
BENCHMARK_CASES: List[Dict[str, Any]] = [
    {
        "id": "B1",
        "task": "帮我检查系统状态",
        "expect_keywords": [],           # 无强约束，检查是否成功即可
        "expect_actions": ["get_system_info", "run_shell", "call_tool"],
        "max_steps": 10,
        "timeout_s": 60,
    },
    {
        "id": "B2",
        "task": (
            "读取 /tmp/_bench_config.json 的内容（如果文件不存在先创建一个包含 {\"port\": 8080} 的文件），"
            "然后把 port 改成 3000 并保存回去"
        ),
        "expect_actions": ["read_file", "write_file"],
        "max_steps": 10,
        "timeout_s": 90,
    },
    {
        "id": "B3",
        "task": "在 /tmp 目录下创建并运行一个简单的 Python HTTP server 脚本（`python3 -m http.server 18099`），后台运行后立即结束任务",
        "expect_actions": ["run_shell"],
        "max_steps": 8,
        "timeout_s": 60,
    },
    {
        "id": "B4",
        "task": "我们什么时候开始的对话？",
        "expect_actions": ["finish"],
        "max_steps": 3,
        "timeout_s": 30,
    },
    {
        "id": "B5",
        "task": "先进入 /tmp 目录，然后列出当前目录的文件",
        "expect_actions": ["list_directory", "run_shell"],
        "max_steps": 8,
        "timeout_s": 60,
    },
    {
        "id": "B6",
        "task": (
            "生成一份简短的 Markdown 格式系统报告（包含 CPU/内存状态），"
            "保存到 /tmp/_bench_report.md"
        ),
        "expect_actions": ["write_file"],
        "max_steps": 15,
        "timeout_s": 120,
    },
    {
        "id": "B7",
        "task": "截一张屏幕图",
        "expect_actions": ["call_tool"],
        "max_steps": 5,
        "timeout_s": 30,
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket 任务提交与等待
# ──────────────────────────────────────────────────────────────────────────────

async def run_single_case(
    ws_url: str,
    case: Dict[str, Any],
    verbose: bool = False,
) -> Dict[str, Any]:
    """通过 WebSocket 发送一个 benchmark 任务，等待完成并返回结果。"""
    task_id = None
    session_id = f"bench_{uuid.uuid4().hex[:8]}"
    start_ts = time.time()
    result = {
        "id": case["id"],
        "task": case["task"],
        "success": False,
        "steps": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "duration_s": 0.0,
        "actions_seen": [],
        "error": None,
        "expect_actions_hit": [],
        "expect_actions_miss": [],
    }

    if not HAS_WEBSOCKETS:
        result["error"] = "websockets package not installed. Run: pip install websockets"
        return result

    try:
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            # 发送自主任务
            payload = json.dumps({
                "type": "autonomous_task",
                "task": case["task"],
                "session_id": session_id,
            })
            await ws.send(payload)

            timeout_s = case.get("timeout_s", 120)
            deadline = time.time() + timeout_s

            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(5.0, deadline - time.time()))
                except asyncio.TimeoutError:
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                mtype = msg.get("type", "")

                if verbose:
                    preview = json.dumps(msg)[:120]
                    print(f"  [{case['id']}] {mtype}: {preview}")

                if mtype == "autonomous_task_accepted":
                    task_id = msg.get("task_id")

                elif mtype == "autonomous_chunk":
                    # 累计 token 数
                    usage = msg.get("usage") or {}
                    result["total_tokens"] += usage.get("total_tokens", 0)
                    result["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    result["completion_tokens"] += usage.get("completion_tokens", 0)
                    # 记录 action 类型
                    action_type = msg.get("action_type") or msg.get("action", {}).get("action_type")
                    if action_type and action_type not in result["actions_seen"]:
                        result["actions_seen"].append(action_type)
                    result["steps"] = msg.get("iteration", result["steps"])

                elif mtype in ("task_complete", "autonomous_task_complete"):
                    success = msg.get("success", False)
                    result["success"] = bool(success)
                    usage = msg.get("usage") or msg.get("token_usage") or {}
                    if usage.get("total_tokens", 0) > 0:
                        result["total_tokens"] = usage.get("total_tokens", 0)
                        result["prompt_tokens"] = usage.get("prompt_tokens", 0)
                        result["completion_tokens"] = usage.get("completion_tokens", 0)
                    result["steps"] = msg.get("total_actions", result["steps"])
                    break

                elif mtype == "error":
                    result["error"] = msg.get("message") or str(msg)
                    break

            else:
                result["error"] = f"timeout after {timeout_s}s"

    except Exception as e:
        result["error"] = str(e)

    result["duration_s"] = round(time.time() - start_ts, 2)

    # 检查期望动作命中情况
    expect = case.get("expect_actions", [])
    for ea in expect:
        ea_lower = ea.lower()
        hit = any(ea_lower in (s or "").lower() for s in result["actions_seen"])
        if hit:
            result["expect_actions_hit"].append(ea)
        else:
            result["expect_actions_miss"].append(ea)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    ws_url = args.url.replace("http://", "ws://").replace("https://", "wss://")
    if not ws_url.endswith("/ws"):
        ws_url = ws_url.rstrip("/") + "/ws"

    # 过滤用例
    selected_ids = {s.strip().upper() for s in args.cases.split(",")} if args.cases else None
    cases = [c for c in BENCHMARK_CASES if selected_ids is None or c["id"] in selected_ids]

    if not cases:
        print(f"No matching cases found for: {args.cases}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"MacAgent Benchmark v3.2 — {len(cases)} case(s)")
    print(f"Target: {ws_url}")
    print(f"{'='*60}\n")

    results: List[Dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']}: {case['task'][:60]}...")
        r = await run_single_case(ws_url, case, verbose=args.verbose)
        icon = "✓" if r["success"] else "✗"
        print(
            f"  {icon} success={r['success']} steps={r['steps']} "
            f"tokens={r['total_tokens']} duration={r['duration_s']}s"
        )
        if r["error"]:
            print(f"  ⚠ error: {r['error']}")
        if r["expect_actions_miss"]:
            print(f"  ⚠ expect_actions not seen: {r['expect_actions_miss']}")
        results.append(r)

    # ── 汇总统计 ──
    total = len(results)
    passed = sum(1 for r in results if r["success"])
    total_tokens = sum(r["total_tokens"] for r in results)
    avg_steps = sum(r["steps"] for r in results) / max(total, 1)
    avg_dur = sum(r["duration_s"] for r in results) / max(total, 1)

    summary = {
        "run_at": datetime.now().isoformat(),
        "ws_url": ws_url,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": f"{passed / total * 100:.1f}%" if total else "N/A",
        "avg_steps": round(avg_steps, 1),
        "avg_duration_s": round(avg_dur, 1),
        "total_tokens": total_tokens,
        "cases": results,
    }

    # ── 输出 ──
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed ({summary['pass_rate']})")
    print(f"Avg steps: {summary['avg_steps']}  Avg duration: {summary['avg_duration_s']}s")
    print(f"Total tokens: {total_tokens}")
    print(f"{'='*60}\n")

    # 写入文件
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Results saved to: {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MacAgent v3.2 内部 Benchmark")
    parser.add_argument("--url", default="http://localhost:8000", help="后端服务 URL（http/https/ws）")
    parser.add_argument("--cases", default="", help="指定用例 ID（逗号分隔，如 B1,B3,B7）；默认全部")
    parser.add_argument("--out", default="./data/benchmark", help="结果输出目录")
    parser.add_argument("--verbose", action="store_true", help="打印每条 WebSocket 消息")
    return parser.parse_args()


if __name__ == "__main__":
    _args = _parse_args()
    asyncio.run(main(_args))
