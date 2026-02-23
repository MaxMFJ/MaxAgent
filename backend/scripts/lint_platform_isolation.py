#!/usr/bin/env python3
"""
Lint: 禁止 tools/ 与 agent/core.py 中出现平台命令或系统 API
规则：osascript、pbcopy、pbpaste、screencapture、open -a、say 等必须通过 runtime adapter
"""

import os
import re
import sys

# 禁止的模式：(pattern, 说明)
FORBIDDEN = [
    (r'\bosascript\b', "禁止直接调用 osascript，使用 runtime_adapter.run_script(lang='applescript')"),
    (r'\bpbcopy\b', "禁止直接调用 pbcopy，使用 runtime_adapter.clipboard_write()"),
    (r'\bpbpaste\b', "禁止直接调用 pbpaste，使用 runtime_adapter.clipboard_read()"),
    (r'\bscreencapture\b', "禁止直接调用 screencapture，使用 runtime_adapter.screenshot_*"),
    (r'open\s+-a\s+', "禁止 open -a，使用 runtime_adapter.open_app()"),
    (r'\bsay\s+', "禁止直接调用 say，使用 runtime_adapter.speak()"),
]

# 排除目录/文件（runtime/ 自身可使用这些命令）
# TODO: dynamic_tool_generator, repair_executor 待迁移
EXCLUDE = [
    "runtime/mac_adapter.py",
    "runtime/linux_adapter.py",
    "runtime/windows_adapter.py",
    "scripts/lint_platform_isolation.py",
    "tools/dynamic_tool_generator.py",  # TODO: 迁移至 adapter
    "agent/self_healing/repair_executor.py",  # TODO: 迁移至 adapter
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS_DIR = os.path.join(ROOT, "tools")
AGENT_DIR = os.path.join(ROOT, "agent")


def relpath(p: str) -> str:
    return os.path.relpath(p, ROOT).replace("\\", "/")


def should_check(path: str) -> bool:
    r = relpath(path)
    for ex in EXCLUDE:
        if ex in r or r.startswith(ex):
            return False
    return True


def scan_dir(d: str, ext: str = ".py") -> list:
    out = []
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith(ext):
                out.append(os.path.join(root, f))
    return out


def main() -> int:
    files = scan_dir(TOOLS_DIR) + scan_dir(AGENT_DIR)
    files = [f for f in files if should_check(f)]
    errors = []

    for path in files:
        with open(path, "r", encoding="utf-8") as fp:
            content = fp.read()
        for pattern, msg in FORBIDDEN:
            for m in re.finditer(pattern, content):
                # 简单排除字符串/注释中的引用（如文档）
                line = content[: m.start()].split("\n")[-1]
                if "# noqa: platform" in line or '"""' in line or "'''" in line:
                    continue
                errors.append((path, m.start(), msg, m.group()))

    if not errors:
        print("✅ 平台隔离检查通过：tools/ 与 agent/ 未直接调用平台命令")
        return 0

    print("❌ 平台隔离违规：以下位置禁止直接使用平台命令\n")
    for path, pos, msg, matched in errors:
        with open(path, "r") as fp:
            lines = fp.read().split("\n")
        line_no = 1
        for i, ln in enumerate(lines):
            if sum(len(l) + 1 for l in lines[:i]) > pos:
                line_no = i + 1
                break
        print(f"  {relpath(path)}:{line_no}")
        print(f"    {msg}")
        print(f"    匹配: {repr(matched)}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
