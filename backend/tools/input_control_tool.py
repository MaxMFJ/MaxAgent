"""
Input Control Tool - 鼠标和键盘控制工具
让 Agent 能够模拟人类的鼠标和键盘操作（通过 RuntimeAdapter 跨平台）
"""

import asyncio
import logging
import os
from typing import Optional, List, Tuple
from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)

# 尝试导入进程内 CGEvent 模块
try:
    from runtime import cg_event as _cg
    _HAS_CG = _cg.HAS_QUARTZ
except Exception:
    _cg = None
    _HAS_CG = False


class InputControlTool(BaseTool):
    """
    鼠标和键盘控制工具
    
    提供完整的输入模拟能力：
    - 鼠标移动、点击、拖拽、滚动
    - 键盘输入、快捷键
    - 屏幕坐标获取
    """
    
    name = "input_control"
    description = """鼠标和键盘控制工具，用于模拟人类输入操作。

支持的操作：
- mouse_move: 移动鼠标到指定位置
- mouse_click: 鼠标点击（左键/右键/双击）
- mouse_drag: 鼠标拖拽
- mouse_scroll: 鼠标滚动
- keyboard_type: 键盘输入文字
- keyboard_key: 按下特定按键
- keyboard_shortcut: 执行快捷键组合
- get_mouse_position: 获取当前鼠标位置
- get_screen_size: 获取屏幕尺寸

使用场景：
- 点击按钮、链接
- 在输入框中输入文字
- 执行快捷键操作（如 Cmd+C, Cmd+V）
- 滚动页面
- 拖拽文件或元素"""
    
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "mouse_move", "mouse_click", "mouse_drag", "mouse_scroll",
                    "keyboard_type", "keyboard_key", "keyboard_shortcut",
                    "get_mouse_position", "get_screen_size"
                ],
                "description": "要执行的操作类型"
            },
            "x": {
                "type": "number",
                "description": "X 坐标（用于鼠标操作）"
            },
            "y": {
                "type": "number",
                "description": "Y 坐标（用于鼠标操作）"
            },
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "鼠标按钮（默认 left）"
            },
            "clicks": {
                "type": "integer",
                "description": "点击次数（1=单击，2=双击）"
            },
            "end_x": {
                "type": "number",
                "description": "拖拽结束 X 坐标"
            },
            "end_y": {
                "type": "number",
                "description": "拖拽结束 Y 坐标"
            },
            "scroll_amount": {
                "type": "integer",
                "description": "滚动量（正数向上，负数向下）"
            },
            "text": {
                "type": "string",
                "description": "要输入的文字"
            },
            "key": {
                "type": "string",
                "description": "要按下的按键（如 return, escape, tab, up, down, left, right）"
            },
            "modifiers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "修饰键列表（command, control, option, shift）"
            },
            "delay": {
                "type": "number",
                "description": "操作前延迟（秒）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        delay = kwargs.get("delay", 0)
        
        if delay > 0:
            await asyncio.sleep(delay)
        
        try:
            if action == "mouse_move":
                return await self._mouse_move(kwargs)
            elif action == "mouse_click":
                return await self._mouse_click(kwargs)
            elif action == "mouse_drag":
                return await self._mouse_drag(kwargs)
            elif action == "mouse_scroll":
                return await self._mouse_scroll(kwargs)
            elif action == "keyboard_type":
                return await self._keyboard_type(kwargs)
            elif action == "keyboard_key":
                return await self._keyboard_key(kwargs)
            elif action == "keyboard_shortcut":
                return await self._keyboard_shortcut(kwargs)
            elif action == "get_mouse_position":
                return await self._get_mouse_position()
            elif action == "get_screen_size":
                return await self._get_screen_size()
            else:
                return ToolResult(success=False, error=f"未知操作: {action}")
        except Exception as e:
            logger.error(f"Input control error: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _run_applescript(self, script: str) -> Tuple[bool, str]:
        """执行 AppleScript（通过 RuntimeAdapter）"""
        adapter = self.runtime_adapter
        if not adapter:
            logger.warning("input_control: runtime_adapter 为 None，无法执行 AppleScript")
            return False, "当前平台不支持 GUI 输入（runtime_adapter 未注入）"
        r = await adapter.run_script(script, "applescript")
        if not r.success:
            logger.warning("AppleScript 执行失败: %s (script: %s)", r.error, script[:80])
        return r.success, r.error or r.output
    
    async def _mouse_move(self, kwargs: dict) -> ToolResult:
        """移动鼠标到指定位置"""
        x, y = kwargs.get("x"), kwargs.get("y")
        if x is None or y is None:
            return ToolResult(success=False, error="需要提供 x 和 y 坐标")
        ix, iy = int(x), int(y)
        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, err = _cg.mouse_move(ix, iy)
            if ok:
                return ToolResult(success=True, data={"action": "mouse_move", "x": ix, "y": iy})
            logger.debug("CGEvent mouse_move 失败: %s, 回退 adapter", err)
        # 回退: adapter (cliclick/AppleScript)
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持 GUI 输入")
        success, err = await adapter.mouse_move(ix, iy)
        if not success:
            return ToolResult(success=False, error=err or "鼠标移动失败")
        return ToolResult(success=True, data={"action": "mouse_move", "x": ix, "y": iy})
    
    async def _run_swift_inline(self, code: str) -> bool:
        """运行内联 Swift 代码"""
        try:
            process = await asyncio.create_subprocess_exec(
                "swift", "-e", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            return process.returncode == 0
        except:
            return False
    
    async def _mouse_click(self, kwargs: dict) -> ToolResult:
        """鼠标点击"""
        x = kwargs.get("x")
        y = kwargs.get("y")
        button = kwargs.get("button", "left")
        clicks = kwargs.get("clicks", 1)

        # 如果没有指定坐标，获取当前位置
        if x is None or y is None:
            if _HAS_CG:
                pos_ok, cx, cy, _ = _cg.get_mouse_position()
                if pos_ok:
                    x, y = cx, cy
            if x is None or y is None:
                pos_result = await self._get_mouse_position()
                if pos_result.success:
                    x = pos_result.data.get("x", 0)
                    y = pos_result.data.get("y", 0)
                else:
                    return ToolResult(success=False, error="无法获取鼠标位置，请提供 x 和 y 坐标")

        ix, iy = int(x), int(y)

        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, err = _cg.mouse_click(ix, iy, button=button, clicks=clicks)
            if ok:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_click", "x": ix, "y": iy, "button": button, "clicks": clicks}
                )
            logger.debug("CGEvent mouse_click 失败: %s, 回退 cliclick", err)

        # 回退: cliclick
        try:
            click_cmd = "c" if button == "left" else ("rc" if button == "right" else "c")
            if clicks == 2:
                click_cmd = "dc"
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"{click_cmd}:{ix},{iy}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_click", "x": ix, "y": iy, "button": button, "clicks": clicks}
                )
        except FileNotFoundError:
            logger.warning("cliclick 未安装或不在 PATH 中（PATH=%s）", os.environ.get("PATH", "")[:120])

        return ToolResult(
            success=False,
            error="鼠标点击失败：CGEvent 和 cliclick 均失败。请确保已授予辅助功能权限，并安装 cliclick: brew install cliclick"
        )
    
    async def _mouse_drag(self, kwargs: dict) -> ToolResult:
        """鼠标拖拽"""
        x = kwargs.get("x")
        y = kwargs.get("y")
        end_x = kwargs.get("end_x")
        end_y = kwargs.get("end_y")

        if None in (x, y, end_x, end_y):
            return ToolResult(success=False, error="拖拽需要提供起始和结束坐标 (x, y, end_x, end_y)")

        ix, iy, iex, iey = int(x), int(y), int(end_x), int(end_y)

        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, err = _cg.mouse_drag(ix, iy, iex, iey)
            if ok:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_drag", "from": [ix, iy], "to": [iex, iey]}
                )
            logger.debug("CGEvent mouse_drag 失败: %s, 回退 cliclick", err)

        # 回退: cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"dd:{ix},{iy}", f"du:{iex},{iey}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_drag", "from": [ix, iy], "to": [iex, iey]}
                )
        except FileNotFoundError:
            pass

        return ToolResult(success=False, error="拖拽失败：请确保已授予辅助功能权限")
    
    async def _mouse_scroll(self, kwargs: dict) -> ToolResult:
        """鼠标滚动"""
        amount = kwargs.get("scroll_amount", -3)
        x = kwargs.get("x")
        y = kwargs.get("y")

        # 如果指定了位置，先移动鼠标
        if x is not None and y is not None:
            await self._mouse_move({"x": x, "y": y})
            await asyncio.sleep(0.1)

        # 优先使用进程内 CGEvent
        if _HAS_CG:
            sx = int(x) if x is not None else None
            sy = int(y) if y is not None else None
            ok, err = _cg.mouse_scroll(int(amount), sx, sy)
            if ok:
                return ToolResult(success=True, data={"action": "mouse_scroll", "amount": amount})
            logger.debug("CGEvent mouse_scroll 失败: %s, 回退 cliclick", err)

        # 回退: cliclick
        try:
            direction = "u" if amount > 0 else "d"
            scroll_count = abs(int(amount))
            for _ in range(scroll_count):
                process = await asyncio.create_subprocess_exec(
                    "cliclick", f"w:{direction}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                await asyncio.sleep(0.05)
            return ToolResult(success=True, data={"action": "mouse_scroll", "amount": amount})
        except FileNotFoundError:
            pass

        return ToolResult(success=False, error="滚动失败：请确保已授予辅助功能权限")
    
    async def _keyboard_type(self, kwargs: dict) -> ToolResult:
        """键盘输入文字（支持中文/Unicode）"""
        text = kwargs.get("text", "")

        if not text:
            return ToolResult(success=False, error="需要提供要输入的文字")

        display = text[:50] + "..." if len(text) > 50 else text

        # 优先使用进程内 CGEvent (支持中文通过剪贴板)
        if _HAS_CG:
            ok, err = await _cg.type_text(text)
            if ok:
                return ToolResult(success=True, data={"action": "keyboard_type", "text": display})
            logger.debug("CGEvent type_text 失败: %s, 回退 cliclick", err)

        # 回退: cliclick (仅 ASCII)
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"t:{text}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                return ToolResult(success=True, data={"action": "keyboard_type", "text": display})
        except FileNotFoundError:
            pass

        # 最终回退: AppleScript
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
        # 检测是否包含非 ASCII（中文等），使用剪贴板粘贴
        has_non_ascii = any(ord(c) > 127 for c in text)
        if has_non_ascii:
            script = (
                f'set the clipboard to "{escaped_text}"\n'
                f'delay 0.1\n'
                f'tell application "System Events"\n'
                f'    keystroke "v" using command down\n'
                f'end tell'
            )
        else:
            script = f'tell application "System Events"\n    keystroke "{escaped_text}"\nend tell'
        success, output = await self._run_applescript(script)
        if not success:
            return ToolResult(success=False, error=f"输入失败: {output}")
        return ToolResult(success=True, data={"action": "keyboard_type", "text": display})
    
    async def _keyboard_key(self, kwargs: dict) -> ToolResult:
        """按下特定按键"""
        key = kwargs.get("key", "")
        modifiers = kwargs.get("modifiers", [])

        if not key:
            return ToolResult(success=False, error="需要提供按键名称")

        key_lower = key.lower()

        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, err = _cg.key_press(key_lower, modifiers)
            if ok:
                return ToolResult(
                    success=True,
                    data={"action": "keyboard_key", "key": key, "modifiers": modifiers}
                )
            logger.debug("CGEvent key_press 失败: %s, 回退 cliclick", err)

        # 回退: cliclick
        try:
            cliclick_key = key_lower
            if key_lower in ["return", "enter"]:
                cliclick_key = "return"
            elif key_lower in ["escape", "esc"]:
                cliclick_key = "esc"
            elif key_lower in ["delete", "backspace"]:
                cliclick_key = "delete"

            modifier_str = ""
            for mod in modifiers:
                ml = mod.lower()
                if ml in ("command", "cmd"):
                    modifier_str += "cmd,"
                elif ml in ("control", "ctrl"):
                    modifier_str += "ctrl,"
                elif ml in ("option", "alt"):
                    modifier_str += "alt,"
                elif ml == "shift":
                    modifier_str += "shift,"

            if modifier_str:
                cmd = f"kp:{modifier_str.rstrip(',')}+{cliclick_key}"
            else:
                cmd = f"kp:{cliclick_key}"

            process = await asyncio.create_subprocess_exec(
                "cliclick", cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "keyboard_key", "key": key, "modifiers": modifiers}
                )
        except FileNotFoundError:
            pass

        # 最终回退: AppleScript key code
        key_codes = {
            "return": 36, "enter": 36, "tab": 48, "space": 49,
            "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
            "up": 126, "down": 125, "left": 123, "right": 124,
            "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
            "f1": 122, "f2": 120, "f3": 99, "f4": 118,
            "f5": 96, "f6": 97, "f7": 98, "f8": 100,
            "f9": 101, "f10": 109, "f11": 103, "f12": 111,
        }
        modifier_using = []
        for mod in modifiers:
            ml = mod.lower()
            if ml in ("command", "cmd"):
                modifier_using.append("command down")
            elif ml in ("control", "ctrl"):
                modifier_using.append("control down")
            elif ml in ("option", "alt"):
                modifier_using.append("option down")
            elif ml == "shift":
                modifier_using.append("shift down")
        using_clause = f" using {{{', '.join(modifier_using)}}}" if modifier_using else ""

        if key_lower in key_codes:
            script = f'tell application "System Events"\n    key code {key_codes[key_lower]}{using_clause}\nend tell'
        else:
            script = f'tell application "System Events"\n    keystroke "{key}"{using_clause}\nend tell'

        success, output = await self._run_applescript(script)
        if not success:
            return ToolResult(success=False, error=f"按键失败: {output}")
        return ToolResult(
            success=True,
            data={"action": "keyboard_key", "key": key, "modifiers": modifiers}
        )
    
    async def _keyboard_shortcut(self, kwargs: dict) -> ToolResult:
        """执行快捷键组合"""
        key = kwargs.get("key", "")
        modifiers = kwargs.get("modifiers", [])

        if not key:
            return ToolResult(success=False, error="需要提供按键")

        # 安全保护：return/enter 不应该通过 keyboard_shortcut 发送
        # LLM 可能误用 keyboard_shortcut(return) 导致 Cmd+Return（不是发送）
        key_lower = key.lower()
        if key_lower in ("return", "enter"):
            logger.warning(
                "keyboard_shortcut 被调用发送 return 键（modifiers=%s），"
                "自动降级为纯 keyboard_key(return) — 发送消息应使用 keyboard_key",
                modifiers
            )
            return await self._keyboard_key({"key": key, "modifiers": []})

        if not modifiers:
            modifiers = ["command"]

        # 直接复用 _keyboard_key（已内置 CGEvent 优先逻辑）
        return await self._keyboard_key({"key": key, "modifiers": modifiers})
    
    async def _get_mouse_position(self) -> ToolResult:
        """获取当前鼠标位置"""
        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, mx, my, err = _cg.get_mouse_position()
            if ok:
                return ToolResult(success=True, data={"x": mx, "y": my})

        # 回退: cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", "p",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                output = stdout.decode().strip()
                parts = output.split(",")
                if len(parts) == 2:
                    return ToolResult(success=True, data={"x": int(parts[0]), "y": int(parts[1])})
        except FileNotFoundError:
            pass

        return ToolResult(success=False, error="无法获取鼠标位置")
    
    async def _get_screen_size(self) -> ToolResult:
        """获取屏幕尺寸"""
        # 优先使用进程内 CGEvent
        if _HAS_CG:
            ok, w, h, err = _cg.get_screen_size()
            if ok:
                return ToolResult(success=True, data={"width": w, "height": h})

        # 回退: system_profiler
        try:
            process = await asyncio.create_subprocess_exec(
                "system_profiler", "SPDisplaysDataType",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            import re
            match = re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", stdout.decode())
            if match:
                return ToolResult(
                    success=True,
                    data={"width": int(match.group(1)), "height": int(match.group(2))}
                )
        except Exception:
            pass

        return ToolResult(success=False, error="无法获取屏幕尺寸")
