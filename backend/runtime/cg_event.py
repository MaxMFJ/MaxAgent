"""
cg_event.py - 纯 Python CGEvent 键鼠操作
替代 cliclick + osascript + python3 三层嵌套，直接在进程内调用 Quartz CGEvent API

依赖: pyobjc-framework-Quartz (已安装)
权限: 需要辅助功能权限 (Accessibility)
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import Quartz
    from Quartz import (
        CGEventCreateMouseEvent,
        CGEventCreateKeyboardEvent,
        CGEventCreateScrollWheelEvent,
        CGEventPost,
        CGEventSetFlags,
        CGEventSetIntegerValueField,
        kCGHIDEventTap,
        kCGEventMouseMoved,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventLeftMouseDragged,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGEventOtherMouseDown,
        kCGEventOtherMouseUp,
        kCGScrollEventUnitLine,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskShift,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskControl,
        kCGMouseButtonLeft,
        kCGMouseButtonRight,
        kCGMouseButtonCenter,
        kCGKeyboardEventKeycode,
        CGDisplayPixelsWide,
        CGDisplayPixelsHigh,
        CGMainDisplayID,
    )
    from AppKit import NSEvent

    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False
    logger.warning("Quartz/AppKit 不可用，CGEvent 键鼠操作将不工作")

# macOS 虚拟按键码映射
KEY_CODES = {
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5,
    "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45,
    "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17, "u": 32,
    "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21,
    "5": 23, "6": 22, "7": 26, "8": 28, "9": 25,
    "return": 36, "enter": 36, "tab": 48, "space": 49,
    "delete": 51, "backspace": 51, "forwarddelete": 117,
    "escape": 53, "esc": 53,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "-": 27, "=": 24, "[": 33, "]": 30,
    "\\": 42, ";": 41, "'": 39, ",": 43,
    ".": 47, "/": 44, "`": 50,
}

# 修饰键映射
MODIFIER_FLAGS = {
    "command": kCGEventFlagMaskCommand if HAS_QUARTZ else 0,
    "cmd": kCGEventFlagMaskCommand if HAS_QUARTZ else 0,
    "shift": kCGEventFlagMaskShift if HAS_QUARTZ else 0,
    "option": kCGEventFlagMaskAlternate if HAS_QUARTZ else 0,
    "alt": kCGEventFlagMaskAlternate if HAS_QUARTZ else 0,
    "control": kCGEventFlagMaskControl if HAS_QUARTZ else 0,
    "ctrl": kCGEventFlagMaskControl if HAS_QUARTZ else 0,
}


def _check_available() -> Optional[str]:
    """检查 CGEvent 是否可用，返回 None 或错误信息"""
    if not HAS_QUARTZ:
        return "Quartz 框架不可用，请安装 pyobjc-framework-Quartz"
    return None


# ===================== 鼠标操作 =====================

def mouse_move(x: int, y: int) -> Tuple[bool, str]:
    """移动鼠标到 (x, y)"""
    err = _check_available()
    if err:
        return False, err
    try:
        event = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, event)
        return True, ""
    except Exception as e:
        return False, f"鼠标移动失败: {e}"


def mouse_click(
    x: int, y: int,
    button: str = "left",
    clicks: int = 1,
) -> Tuple[bool, str]:
    """
    鼠标点击
    button: left/right/middle
    clicks: 1=单击, 2=双击
    """
    err = _check_available()
    if err:
        return False, err

    try:
        if button == "right":
            down_type = kCGEventRightMouseDown
            up_type = kCGEventRightMouseUp
            btn = kCGMouseButtonRight
        elif button == "middle":
            down_type = kCGEventOtherMouseDown
            up_type = kCGEventOtherMouseUp
            btn = kCGMouseButtonCenter
        else:
            down_type = kCGEventLeftMouseDown
            up_type = kCGEventLeftMouseUp
            btn = kCGMouseButtonLeft

        point = (x, y)

        # 先移动到目标位置
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, btn)
        CGEventPost(kCGHIDEventTap, move)
        time.sleep(0.02)

        for i in range(clicks):
            down = CGEventCreateMouseEvent(None, down_type, point, btn)
            up = CGEventCreateMouseEvent(None, up_type, point, btn)

            # 设置 clickCount（双击需要）
            if clicks == 2:
                CGEventSetIntegerValueField(down, Quartz.kCGMouseEventClickState, i + 1)
                CGEventSetIntegerValueField(up, Quartz.kCGMouseEventClickState, i + 1)

            CGEventPost(kCGHIDEventTap, down)
            time.sleep(0.01)
            CGEventPost(kCGHIDEventTap, up)

            if i < clicks - 1:
                time.sleep(0.05)

        return True, ""
    except Exception as e:
        return False, f"鼠标点击失败: {e}"


def mouse_drag(
    start_x: int, start_y: int,
    end_x: int, end_y: int,
    duration: float = 0.3,
    steps: int = 20,
) -> Tuple[bool, str]:
    """平滑鼠标拖拽"""
    err = _check_available()
    if err:
        return False, err

    try:
        start = (start_x, start_y)
        end = (end_x, end_y)

        # 移动到起始位置
        move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, start, kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, move)
        time.sleep(0.05)

        # 按下
        down = CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, start, kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, down)
        time.sleep(0.02)

        # 平滑拖拽
        step_delay = duration / steps
        for i in range(1, steps + 1):
            t = i / steps
            cx = start_x + (end_x - start_x) * t
            cy = start_y + (end_y - start_y) * t
            drag = CGEventCreateMouseEvent(None, kCGEventLeftMouseDragged, (cx, cy), kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, drag)
            time.sleep(step_delay)

        # 释放
        up = CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, end, kCGMouseButtonLeft)
        CGEventPost(kCGHIDEventTap, up)
        return True, ""
    except Exception as e:
        return False, f"鼠标拖拽失败: {e}"


def mouse_scroll(amount: int, x: Optional[int] = None, y: Optional[int] = None) -> Tuple[bool, str]:
    """
    鼠标滚动
    amount: 正数向上，负数向下
    """
    err = _check_available()
    if err:
        return False, err

    try:
        # 如果指定了位置，先移动鼠标
        if x is not None and y is not None:
            move = CGEventCreateMouseEvent(None, kCGEventMouseMoved, (x, y), kCGMouseButtonLeft)
            CGEventPost(kCGHIDEventTap, move)
            time.sleep(0.02)

        scroll = CGEventCreateScrollWheelEvent(None, kCGScrollEventUnitLine, 1, amount)
        CGEventPost(kCGHIDEventTap, scroll)
        return True, ""
    except Exception as e:
        return False, f"滚动失败: {e}"


def get_mouse_position() -> Tuple[bool, int, int, str]:
    """获取鼠标位置，返回 (success, x, y, error)"""
    err = _check_available()
    if err:
        return False, 0, 0, err

    try:
        loc = NSEvent.mouseLocation()
        screen_height = CGDisplayPixelsHigh(CGMainDisplayID())
        # NSEvent 的 y 轴是从底部开始的，需要翻转
        x = int(loc.x)
        y = int(screen_height - loc.y)
        return True, x, y, ""
    except Exception as e:
        return False, 0, 0, f"获取鼠标位置失败: {e}"


def get_screen_size() -> Tuple[bool, int, int, str]:
    """获取主屏幕尺寸，返回 (success, width, height, error)"""
    err = _check_available()
    if err:
        return False, 0, 0, err

    try:
        w = CGDisplayPixelsWide(CGMainDisplayID())
        h = CGDisplayPixelsHigh(CGMainDisplayID())
        return True, w, h, ""
    except Exception as e:
        return False, 0, 0, f"获取屏幕尺寸失败: {e}"


# ===================== 键盘操作 =====================

def _resolve_key_code(key: str) -> Optional[int]:
    """解析按键名到虚拟按键码"""
    return KEY_CODES.get(key.lower())


def _resolve_modifier_flags(modifiers: list) -> int:
    """解析修饰键列表到 flag 值"""
    flags = 0
    for mod in modifiers:
        flag = MODIFIER_FLAGS.get(mod.lower(), 0)
        flags |= flag
    return flags


def key_press(key: str, modifiers: Optional[list] = None) -> Tuple[bool, str]:
    """
    按下并释放一个按键，可搭配修饰键
    key: 按键名 (如 "a", "return", "tab", "f1")
    modifiers: 修饰键列表 (如 ["command", "shift"])
    """
    err = _check_available()
    if err:
        return False, err

    modifiers = modifiers or []
    key_code = _resolve_key_code(key)
    if key_code is None:
        return False, f"不支持的按键: {key}"

    try:
        flags = _resolve_modifier_flags(modifiers)

        # key down — 始终显式设置 flags，清除系统继承的修饰键状态
        #（输入法可能残留内部 modifier，导致 return 被当作 shift+return）
        down = CGEventCreateKeyboardEvent(None, key_code, True)
        CGEventSetFlags(down, flags)
        CGEventPost(kCGHIDEventTap, down)

        time.sleep(0.01)

        # key up
        up = CGEventCreateKeyboardEvent(None, key_code, False)
        CGEventSetFlags(up, flags)
        CGEventPost(kCGHIDEventTap, up)

        return True, ""
    except Exception as e:
        return False, f"按键失败: {e}"


def type_text_ascii(text: str) -> Tuple[bool, str]:
    """
    逐字符输入 ASCII 文本（英文、数字、符号）
    对于中文/非 ASCII，请使用 type_text_via_clipboard
    """
    err = _check_available()
    if err:
        return False, err

    try:
        for ch in text:
            key_code = _resolve_key_code(ch.lower())
            if key_code is not None:
                shift = ch.isupper() or ch in '~!@#$%^&*()_+{}|:"<>?'
                flags = kCGEventFlagMaskShift if shift else 0

                down = CGEventCreateKeyboardEvent(None, key_code, True)
                up = CGEventCreateKeyboardEvent(None, key_code, False)
                # 始终显式设置 flags，清除继承的修饰键状态
                CGEventSetFlags(down, flags)
                CGEventSetFlags(up, flags)

                CGEventPost(kCGHIDEventTap, down)
                time.sleep(0.005)
                CGEventPost(kCGHIDEventTap, up)
                time.sleep(0.005)
            elif ch == " ":
                key_press("space")
            elif ch == "\n":
                key_press("return")
            elif ch == "\t":
                key_press("tab")
            else:
                # 无法映射的字符，跳过或用剪贴板方式
                logger.debug(f"跳过无法映射的字符: {ch!r}")
                continue

        return True, ""
    except Exception as e:
        return False, f"文本输入失败: {e}"


async def type_text_via_clipboard(text: str) -> Tuple[bool, str]:
    """
    通过剪贴板粘贴方式输入文本（支持中文和所有 Unicode）
    流程: 保存剪贴板 → 写入文本 → Cmd+V → 恢复剪贴板
    """
    err = _check_available()
    if err:
        return False, err

    try:
        import subprocess

        # 保存当前剪贴板内容
        try:
            saved = subprocess.run(
                ["pbpaste"], capture_output=True, timeout=2
            ).stdout
        except Exception:
            saved = None

        # 写入要输入的文本到剪贴板
        proc = subprocess.run(
            ["pbcopy"], input=text.encode("utf-8"),
            capture_output=True, timeout=2
        )
        if proc.returncode != 0:
            return False, "写入剪贴板失败"

        await asyncio.sleep(0.05)

        # Cmd+V 粘贴
        ok, err_msg = key_press("v", ["command"])
        if not ok:
            return False, f"粘贴失败: {err_msg}"

        await asyncio.sleep(0.1)

        # 恢复剪贴板（异步，不阻塞）
        if saved is not None:
            try:
                subprocess.run(
                    ["pbcopy"], input=saved,
                    capture_output=True, timeout=2
                )
            except Exception:
                pass  # 恢复失败不影响主操作

        return True, ""
    except Exception as e:
        return False, f"剪贴板输入失败: {e}"


async def type_text(text: str, use_clipboard_for_cjk: bool = True) -> Tuple[bool, str]:
    """
    智能文本输入：
    - 纯 ASCII 文本：逐字符 CGEvent
    - 包含中文/Unicode：剪贴板粘贴
    """
    if not text:
        return False, "文本不能为空"

    # 检测是否有非 ASCII 字符
    has_non_ascii = any(ord(c) > 127 for c in text)

    if has_non_ascii and use_clipboard_for_cjk:
        return await type_text_via_clipboard(text)
    else:
        return type_text_ascii(text)
