"""
Input Control Tool - 鼠标和键盘控制工具
让 Agent 能够模拟人类的鼠标和键盘操作（通过 RuntimeAdapter 跨平台）
"""

import asyncio
import logging
from typing import Optional, List, Tuple
from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)


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
            return False, "当前平台不支持 GUI 输入"
        r = await adapter.run_script(script, "applescript")
        return r.success, r.error or r.output
    
    async def _mouse_move(self, kwargs: dict) -> ToolResult:
        """移动鼠标到指定位置"""
        x, y = kwargs.get("x"), kwargs.get("y")
        if x is None or y is None:
            return ToolResult(success=False, error="需要提供 x 和 y 坐标")
        adapter = self.runtime_adapter
        if not adapter:
            return ToolResult(success=False, error="当前平台不支持 GUI 输入")
        success, err = await adapter.mouse_move(int(x), int(y))
        if not success:
            return ToolResult(success=False, error=err or "鼠标移动失败")
        return ToolResult(success=True, data={"action": "mouse_move", "x": x, "y": y})
    
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
        
        # 如果没有指定坐标，使用当前位置
        if x is None or y is None:
            pos_result = await self._get_mouse_position()
            if pos_result.success:
                x = pos_result.data.get("x", 0)
                y = pos_result.data.get("y", 0)
            else:
                return ToolResult(success=False, error="无法获取鼠标位置，请提供 x 和 y 坐标")
        
        # 尝试使用 cliclick
        try:
            click_cmd = "c" if button == "left" else ("rc" if button == "right" else "c")
            if clicks == 2:
                click_cmd = "dc"  # double click
            
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"{click_cmd}:{int(x)},{int(y)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_click", "x": x, "y": y, "button": button, "clicks": clicks}
                )
        except FileNotFoundError:
            pass
        
        # 备用方案：AppleScript
        button_code = 0 if button == "left" else (1 if button == "right" else 2)
        
        script = f'''
do shell script "python3 -c \\"
import Quartz
import time

point = ({x}, {y})
# Move to position first
move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
time.sleep(0.05)

# Click
for i in range({clicks}):
    down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, 0)
    up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    if i < {clicks} - 1:
        time.sleep(0.1)
\\""
'''
        success, output = await self._run_applescript(script)
        
        if not success:
            return ToolResult(success=False, error=f"点击失败: {output}。请安装 cliclick: brew install cliclick")
        
        return ToolResult(
            success=True,
            data={"action": "mouse_click", "x": x, "y": y, "button": button, "clicks": clicks}
        )
    
    async def _mouse_drag(self, kwargs: dict) -> ToolResult:
        """鼠标拖拽"""
        x = kwargs.get("x")
        y = kwargs.get("y")
        end_x = kwargs.get("end_x")
        end_y = kwargs.get("end_y")
        
        if None in (x, y, end_x, end_y):
            return ToolResult(success=False, error="拖拽需要提供起始和结束坐标 (x, y, end_x, end_y)")
        
        # 使用 cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"dd:{int(x)},{int(y)}", f"du:{int(end_x)},{int(end_y)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "mouse_drag", "from": [x, y], "to": [end_x, end_y]}
                )
        except FileNotFoundError:
            pass
        
        # 备用方案
        script = f'''
do shell script "python3 -c \\"
import Quartz
import time

start = ({x}, {y})
end = ({end_x}, {end_y})

# Move to start
move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, start, 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
time.sleep(0.1)

# Mouse down
down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, start, 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
time.sleep(0.05)

# Drag
steps = 20
for i in range(steps + 1):
    t = i / steps
    cx = start[0] + (end[0] - start[0]) * t
    cy = start[1] + (end[1] - start[1]) * t
    drag = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, (cx, cy), 0)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag)
    time.sleep(0.01)

# Mouse up
up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, end, 0)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
\\""
'''
        success, output = await self._run_applescript(script)
        
        if not success:
            return ToolResult(success=False, error=f"拖拽失败: {output}")
        
        return ToolResult(
            success=True,
            data={"action": "mouse_drag", "from": [x, y], "to": [end_x, end_y]}
        )
    
    async def _mouse_scroll(self, kwargs: dict) -> ToolResult:
        """鼠标滚动"""
        amount = kwargs.get("scroll_amount", -3)
        x = kwargs.get("x")
        y = kwargs.get("y")
        
        # 如果指定了位置，先移动鼠标
        if x is not None and y is not None:
            await self._mouse_move({"x": x, "y": y})
            await asyncio.sleep(0.1)
        
        # 使用 cliclick 滚动
        try:
            # cliclick 的滚动语法
            direction = "u" if amount > 0 else "d"
            scroll_count = abs(amount)
            
            for _ in range(scroll_count):
                process = await asyncio.create_subprocess_exec(
                    "cliclick", f"w:{direction}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                await asyncio.sleep(0.05)
            
            return ToolResult(
                success=True,
                data={"action": "mouse_scroll", "amount": amount}
            )
        except FileNotFoundError:
            pass
        
        # 备用方案
        script = f'''
do shell script "python3 -c \\"
import Quartz

scroll = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, {amount})
Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll)
\\""
'''
        success, output = await self._run_applescript(script)
        
        if not success:
            return ToolResult(success=False, error=f"滚动失败: {output}")
        
        return ToolResult(success=True, data={"action": "mouse_scroll", "amount": amount})
    
    async def _keyboard_type(self, kwargs: dict) -> ToolResult:
        """键盘输入文字"""
        text = kwargs.get("text", "")
        
        if not text:
            return ToolResult(success=False, error="需要提供要输入的文字")
        
        # 使用 cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"t:{text}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if process.returncode == 0:
                return ToolResult(
                    success=True,
                    data={"action": "keyboard_type", "text": text[:50] + "..." if len(text) > 50 else text}
                )
        except FileNotFoundError:
            pass
        
        # 备用方案：AppleScript
        escaped_text = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'''
tell application "System Events"
    keystroke "{escaped_text}"
end tell
'''
        success, output = await self._run_applescript(script)
        
        if not success:
            return ToolResult(success=False, error=f"输入失败: {output}")
        
        return ToolResult(
            success=True,
            data={"action": "keyboard_type", "text": text[:50] + "..." if len(text) > 50 else text}
        )
    
    async def _keyboard_key(self, kwargs: dict) -> ToolResult:
        """按下特定按键"""
        key = kwargs.get("key", "")
        modifiers = kwargs.get("modifiers", [])
        
        if not key:
            return ToolResult(success=False, error="需要提供按键名称")
        
        # 按键映射
        key_codes = {
            "return": 36, "enter": 36,
            "tab": 48,
            "space": 49,
            "delete": 51, "backspace": 51,
            "escape": 53, "esc": 53,
            "up": 126,
            "down": 125,
            "left": 123,
            "right": 124,
            "home": 115,
            "end": 119,
            "pageup": 116,
            "pagedown": 121,
            "f1": 122, "f2": 120, "f3": 99, "f4": 118,
            "f5": 96, "f6": 97, "f7": 98, "f8": 100,
            "f9": 101, "f10": 109, "f11": 103, "f12": 111,
        }
        
        key_lower = key.lower()
        
        # 使用 cliclick
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
                if mod.lower() in ["command", "cmd"]:
                    modifier_str += "cmd,"
                elif mod.lower() in ["control", "ctrl"]:
                    modifier_str += "ctrl,"
                elif mod.lower() in ["option", "alt"]:
                    modifier_str += "alt,"
                elif mod.lower() == "shift":
                    modifier_str += "shift,"
            
            if modifier_str:
                modifier_str = modifier_str.rstrip(",")
                cmd = f"kp:{modifier_str}+{cliclick_key}"
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
        
        # 备用方案：AppleScript
        modifier_using = []
        for mod in modifiers:
            if mod.lower() in ["command", "cmd"]:
                modifier_using.append("command down")
            elif mod.lower() in ["control", "ctrl"]:
                modifier_using.append("control down")
            elif mod.lower() in ["option", "alt"]:
                modifier_using.append("option down")
            elif mod.lower() == "shift":
                modifier_using.append("shift down")
        
        using_clause = ""
        if modifier_using:
            using_clause = f" using {{{', '.join(modifier_using)}}}"
        
        if key_lower in key_codes:
            script = f'''
tell application "System Events"
    key code {key_codes[key_lower]}{using_clause}
end tell
'''
        else:
            script = f'''
tell application "System Events"
    keystroke "{key}"{using_clause}
end tell
'''
        
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
        
        if not modifiers:
            modifiers = ["command"]  # 默认使用 Command 键
        
        return await self._keyboard_key({"key": key, "modifiers": modifiers})
    
    async def _get_mouse_position(self) -> ToolResult:
        """获取当前鼠标位置"""
        # 使用 cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", "p",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode().strip()
                # 格式: x,y
                parts = output.split(",")
                if len(parts) == 2:
                    return ToolResult(
                        success=True,
                        data={"x": int(parts[0]), "y": int(parts[1])}
                    )
        except FileNotFoundError:
            pass
        
        # 备用方案：Python
        script = '''
do shell script "python3 -c \\"
import Quartz
loc = Quartz.NSEvent.mouseLocation()
screen_height = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
print(f\\\\\\"{int(loc.x)},{int(screen_height - loc.y)}\\\\\\")
\\""
'''
        success, output = await self._run_applescript(script)
        
        if success and "," in output:
            parts = output.split(",")
            if len(parts) == 2:
                return ToolResult(
                    success=True,
                    data={"x": int(parts[0]), "y": int(parts[1])}
                )
        
        return ToolResult(success=False, error="无法获取鼠标位置")
    
    async def _get_screen_size(self) -> ToolResult:
        """获取屏幕尺寸"""
        script = '''
do shell script "python3 -c \\"
import Quartz
w = Quartz.CGDisplayPixelsWide(Quartz.CGMainDisplayID())
h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
print(f\\\\\\"{w},{h}\\\\\\")
\\""
'''
        success, output = await self._run_applescript(script)
        
        if success and "," in output:
            parts = output.split(",")
            if len(parts) == 2:
                return ToolResult(
                    success=True,
                    data={"width": int(parts[0]), "height": int(parts[1])}
                )
        
        # 备用方案：使用 system_profiler
        try:
            process = await asyncio.create_subprocess_exec(
                "system_profiler", "SPDisplaysDataType",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            output = stdout.decode()
            
            # 解析 Resolution 行
            import re
            match = re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", output)
            if match:
                return ToolResult(
                    success=True,
                    data={"width": int(match.group(1)), "height": int(match.group(2))}
                )
        except:
            pass
        
        return ToolResult(success=False, error="无法获取屏幕尺寸")
