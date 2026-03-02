#!/usr/bin/env python3
"""
CGEvent 集成测试脚本
用于验证 cg_event.py 是否正确集成到 input_control_tool.py 和 mac_adapter.py

运行方式:
  cd backend
  python -m tests.test_cg_event_integration          # 运行全部测试
  python -m tests.test_cg_event_integration --quick   # 仅模块检查，不执行实际 GUI 操作
  python -m tests.test_cg_event_integration --live    # 包含实际鼠标/键盘操作（需辅助功能权限）
"""

import sys
import os
import asyncio
import importlib
import argparse

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = {"pass": 0, "fail": 0, "warn": 0}


def report(ok: bool, msg: str, warn=False):
    if warn:
        results["warn"] += 1
        print(f"  {WARN} {msg}")
    elif ok:
        results["pass"] += 1
        print(f"  {PASS} {msg}")
    else:
        results["fail"] += 1
        print(f"  {FAIL} {msg}")


# ========== 阶段 1: 模块导入检查 ==========
def test_import_cg_event():
    """检查 cg_event 模块能否导入"""
    print("\n[阶段 1] 模块导入检查")
    try:
        from runtime import cg_event
        report(True, "runtime.cg_event 导入成功")
        report(cg_event.HAS_QUARTZ, f"Quartz 可用: {cg_event.HAS_QUARTZ}")
        return cg_event
    except ImportError as e:
        report(False, f"runtime.cg_event 导入失败: {e}")
        return None


def test_import_input_control():
    """检查 input_control_tool 是否正确引用 cg_event"""
    try:
        # 读取源码检查
        tool_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tools", "input_control_tool.py"
        )
        with open(tool_path) as f:
            src = f.read()

        report("from runtime import cg_event" in src, "input_control_tool.py 包含 cg_event 导入")
        report("_HAS_CG" in src, "input_control_tool.py 包含 _HAS_CG 标志")

        # 检查所有方法是否使用了 CGEvent 优先路径
        methods_with_cg = [
            ("_mouse_move", "_cg.mouse_move"),
            ("_mouse_click", "_cg.mouse_click"),
            ("_mouse_drag", "_cg.mouse_drag"),
            ("_mouse_scroll", "_cg.mouse_scroll"),
            ("_keyboard_type", "_cg.type_text"),
            ("_keyboard_key", "_cg.key_press"),
            ("_get_mouse_position", "_cg.get_mouse_position"),
            ("_get_screen_size", "_cg.get_screen_size"),
        ]

        for method_name, cg_call in methods_with_cg:
            # 找到方法体
            idx = src.find(f"def {method_name}")
            if idx == -1:
                report(False, f"未找到方法 {method_name}")
                continue
            # 截取到下一个 def
            next_def = src.find("\n    async def ", idx + 1)
            if next_def == -1:
                next_def = len(src)
            body = src[idx:next_def]
            has_cg = cg_call in body
            report(has_cg, f"{method_name} → 使用 {cg_call}")

        # 检查不应存在的旧模式
        old_patterns = [
            ('do shell script "python3 -c', "嵌套 python3 -c 调用"),
            ("Quartz.CGEventCreateMouseEvent", "直接字符串中的 Quartz.CGEvent 调用"),
        ]
        for pattern, desc in old_patterns:
            found = pattern in src
            if found:
                report(False, f"发现旧模式残留: {desc}")
            else:
                report(True, f"已移除旧模式: {desc}")

    except Exception as e:
        report(False, f"检查 input_control_tool.py 失败: {e}")


def test_import_mac_adapter():
    """检查 mac_adapter 是否正确引用 cg_event"""
    try:
        adapter_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "runtime", "mac_adapter.py"
        )
        with open(adapter_path) as f:
            src = f.read()

        report("from . import cg_event as _cg" in src, "mac_adapter.py 包含 cg_event 导入")

        adapter_checks = [
            ("mouse_move", "_cg.mouse_move"),
            ("mouse_click", "_cg.mouse_click"),
            ("type_text", "_cg.type_text"),
        ]
        for method_name, cg_call in adapter_checks:
            idx = src.find(f"async def {method_name}")
            if idx == -1:
                report(False, f"未找到方法 {method_name}")
                continue
            next_def = src.find("\n    async def ", idx + 1)
            if next_def == -1:
                next_def = len(src)
            body = src[idx:next_def]
            has_cg = cg_call in body
            report(has_cg, f"mac_adapter.{method_name} → 使用 {cg_call}")

    except Exception as e:
        report(False, f"检查 mac_adapter.py 失败: {e}")


def test_requirements():
    """检查 requirements 文件是否包含 pyobjc 依赖"""
    print("\n[阶段 1b] 依赖检查")
    for fname in ("requirements.txt", "requirements-core.txt"):
        fpath = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), fname
        )
        try:
            with open(fpath) as f:
                content = f.read()
            has_quartz = "pyobjc-framework-Quartz" in content
            has_appsvcs = "pyobjc-framework-ApplicationServices" in content
            report(has_quartz, f"{fname} 包含 pyobjc-framework-Quartz")
            report(has_appsvcs, f"{fname} 包含 pyobjc-framework-ApplicationServices")
        except FileNotFoundError:
            report(False, f"{fname} 不存在")


# ========== 阶段 2: CGEvent API 直接测试 ==========
def test_cg_event_api(cg_event):
    """直接测试 cg_event 模块的函数"""
    print("\n[阶段 2] CGEvent API 直接测试")

    if not cg_event or not cg_event.HAS_QUARTZ:
        report(False, "跳过: Quartz 不可用", warn=True)
        return

    # get_screen_size
    ok, w, h, err = cg_event.get_screen_size()
    report(ok and w > 0 and h > 0, f"get_screen_size → {w}x{h}")

    # get_mouse_position
    ok, x, y, err = cg_event.get_mouse_position()
    report(ok, f"get_mouse_position → ({x}, {y})")


# ========== 阶段 3: 实际 GUI 操作测试 (可选) ==========
async def test_live_operations(cg_event):
    """需要辅助功能权限，会实际移动鼠标和按键"""
    print("\n[阶段 3] 实际 GUI 操作测试 (需辅助功能权限)")

    if not cg_event or not cg_event.HAS_QUARTZ:
        report(False, "跳过: Quartz 不可用", warn=True)
        return

    # 保存当前鼠标位置
    ok, orig_x, orig_y, _ = cg_event.get_mouse_position()
    if not ok:
        report(False, "无法获取初始鼠标位置")
        return

    print(f"  当前鼠标位置: ({orig_x}, {orig_y})")

    # 测试 mouse_move
    target_x, target_y = 100, 100
    ok, err = cg_event.mouse_move(target_x, target_y)
    report(ok, f"mouse_move({target_x}, {target_y}) → ok={ok}")
    await asyncio.sleep(0.3)

    # 验证位置
    ok2, cur_x, cur_y, _ = cg_event.get_mouse_position()
    close_enough = abs(cur_x - target_x) < 5 and abs(cur_y - target_y) < 5
    report(close_enough, f"位置验证: 目标({target_x},{target_y}) 实际({cur_x},{cur_y})")

    # 测试 mouse_move 到另一个位置
    ok, err = cg_event.mouse_move(200, 200)
    await asyncio.sleep(0.3)
    ok2, cur_x, cur_y, _ = cg_event.get_mouse_position()
    close_enough = abs(cur_x - 200) < 5 and abs(cur_y - 200) < 5
    report(close_enough, f"mouse_move(200,200) 验证: 实际({cur_x},{cur_y})")

    # 测试 mouse_scroll
    ok, err = cg_event.mouse_scroll(-3)
    report(ok, f"mouse_scroll(-3) → ok={ok}")
    await asyncio.sleep(0.3)

    # 测试 key_press (不带修饰键)
    # 注意：这会实际按键，可能在当前窗口输入
    print(f"  {WARN} 以下测试会实际按键，请确保焦点在安全位置")
    await asyncio.sleep(1)

    ok, err = cg_event.key_press("space", [])
    report(ok, f"key_press('space', []) → ok={ok}")
    await asyncio.sleep(0.2)

    # 恢复鼠标位置
    cg_event.mouse_move(orig_x, orig_y)
    print(f"  鼠标已恢复到 ({orig_x}, {orig_y})")


def main():
    parser = argparse.ArgumentParser(description="CGEvent 集成测试")
    parser.add_argument("--quick", action="store_true", help="仅模块检查，不执行 CGEvent API")
    parser.add_argument("--live", action="store_true", help="包含实际 GUI 操作测试")
    args = parser.parse_args()

    print("=" * 60)
    print("CGEvent 集成测试")
    print("=" * 60)

    # 阶段 1: 模块检查
    cg = test_import_cg_event()
    test_import_input_control()
    test_import_mac_adapter()
    test_requirements()

    if args.quick:
        print("\n(--quick 模式，跳过 API 和 GUI 测试)")
    else:
        # 阶段 2: CGEvent API 测试
        test_cg_event_api(cg)

        # 阶段 3: 实际 GUI 操作
        if args.live:
            asyncio.run(test_live_operations(cg))
        else:
            print(f"\n  {WARN} 跳过实际 GUI 操作测试 (使用 --live 启用)")

    # 汇总
    print("\n" + "=" * 60)
    total = results["pass"] + results["fail"] + results["warn"]
    print(f"总计: {total} 项  |  {PASS} 通过: {results['pass']}  |  {FAIL} 失败: {results['fail']}  |  {WARN} 警告: {results['warn']}")
    print("=" * 60)

    if results["fail"] > 0:
        print("\n⚠️  存在失败项，请检查上述输出")
        sys.exit(1)
    else:
        print("\n🎉 全部通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
