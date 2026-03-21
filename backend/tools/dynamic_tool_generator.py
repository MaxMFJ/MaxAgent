"""
Dynamic Tool Generator - 动态工具生成器
让 Agent 能够自主生成新工具来完成未知任务
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)

# 生成的工具保存目录
GENERATED_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "generated_tools")
os.makedirs(GENERATED_TOOLS_DIR, exist_ok=True)


class DynamicToolGenerator(BaseTool):
    """
    动态工具生成器 - 让 Agent 能够创建新工具
    
    核心能力：
    1. 生成 AppleScript 来控制 macOS GUI
    2. 生成 Python 脚本来扩展功能
    3. 测试生成的脚本
    4. 保存成功的脚本为可复用工具
    """
    
    name = "dynamic_tool"
    description = """动态工具生成器，用于创建新工具来完成当前工具无法完成的任务。

支持的操作：
- generate_applescript: 生成 AppleScript 来控制 GUI
- generate_python: 生成 Python 脚本
- test_script: 测试脚本是否可用
- save_tool: 保存脚本为可复用工具
- list_tools: 列出已生成的工具
- run_saved_tool: 运行已保存的工具

使用场景：
- 控制特定应用的 GUI（点击按钮、输入文本等）
- 执行复杂的自动化流程
- 创建可复用的自动化脚本"""
    
    category = ToolCategory.CUSTOM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate_applescript", "generate_python", "test_script", 
                        "save_tool", "list_tools", "run_saved_tool"],
                "description": "要执行的操作"
            },
            "task_description": {
                "type": "string",
                "description": "任务描述（用于生成脚本）"
            },
            "script_content": {
                "type": "string",
                "description": "要测试或保存的脚本内容"
            },
            "script_type": {
                "type": "string",
                "enum": ["applescript", "python", "shell"],
                "description": "脚本类型"
            },
            "tool_name": {
                "type": "string",
                "description": "工具名称（用于保存或运行）"
            },
            "tool_args": {
                "type": "object",
                "description": "运行已保存工具时的参数"
            }
        },
        "required": ["action"]
    }
    
    # 常用的 AppleScript 模板
    APPLESCRIPT_TEMPLATES = {
        "click_menu": '''
tell application "System Events"
    tell process "{app_name}"
        click menu item "{menu_item}" of menu "{menu}" of menu bar 1
    end tell
end tell
''',
        "click_button": '''
tell application "System Events"
    tell process "{app_name}"
        click button "{button_name}" of window 1
    end tell
end tell
''',
        "get_window_info": '''
tell application "System Events"
    tell process "{app_name}"
        set winList to every window
        set winInfo to {{}}
        repeat with w in winList
            set winName to name of w
            set winPos to position of w
            set winSize to size of w
            set end of winInfo to {{name:winName, position:winPos, size:winSize}}
        end repeat
        return winInfo
    end tell
end tell
''',
        "get_ui_elements": '''
tell application "System Events"
    tell process "{app_name}"
        set uiElements to entire contents of window 1
        set elementInfo to {{}}
        repeat with elem in uiElements
            try
                set elemClass to class of elem as string
                set elemName to name of elem
                set end of elementInfo to {{class:elemClass, name:elemName}}
            end try
        end repeat
        return elementInfo
    end tell
end tell
''',
        "click_at_position": '''
tell application "System Events"
    click at {{{x}, {y}}}
end tell
''',
        "type_text": '''
tell application "System Events"
    tell process "{app_name}"
        keystroke "{text}"
    end tell
end tell
''',
        "activate_and_wait": '''
tell application "{app_name}"
    activate
end tell
delay {delay}
'''
    }
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        
        if action == "generate_applescript":
            return await self._generate_applescript(kwargs)
        elif action == "generate_python":
            return await self._generate_python(kwargs)
        elif action == "test_script":
            return await self._test_script(kwargs)
        elif action == "save_tool":
            return await self._save_tool(kwargs)
        elif action == "list_tools":
            return await self._list_tools()
        elif action == "run_saved_tool":
            return await self._run_saved_tool(kwargs)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _generate_applescript(self, kwargs: Dict[str, Any]) -> ToolResult:
        """根据任务描述生成 AppleScript"""
        task = kwargs.get("task_description", "")
        
        if not task:
            return ToolResult(success=False, error="需要提供 task_description")
        
        # 分析任务并选择合适的模板
        script_parts = []
        suggestions = []
        
        # 关键词匹配来选择模板
        task_lower = task.lower()
        
        if "微信" in task or "wechat" in task_lower:
            app_name = "微信"
            # 获取窗口信息
            script_parts.append(self.APPLESCRIPT_TEMPLATES["activate_and_wait"].format(
                app_name=app_name, delay=1
            ))
            
            if "二维码" in task or "qrcode" in task_lower:
                suggestions.append("微信登录二维码通常在窗口中央，建议先截取整个窗口")
                script_parts.append(f'''
-- 获取微信窗口位置和大小
tell application "System Events"
    tell process "微信"
        set winPos to position of window 1
        set winSize to size of window 1
        return {{position:winPos, size:winSize}}
    end tell
end tell
''')
        
        if "截图" in task or "screenshot" in task_lower:
            suggestions.append("可以使用 screencapture 命令截取特定区域")
            script_parts.append('''
-- 截取指定区域（需要替换坐标）
do shell script "screencapture -R{x},{y},{width},{height} /tmp/screenshot.png"
''')
        
        if "点击" in task or "click" in task_lower:
            suggestions.append("需要先获取 UI 元素信息来确定点击位置")
            script_parts.append(self.APPLESCRIPT_TEMPLATES["get_ui_elements"].format(
                app_name=kwargs.get("app_name", "目标应用")
            ))
        
        # 组合脚本
        full_script = "\n".join(script_parts) if script_parts else f'''
-- 根据任务生成的脚本框架
-- 任务: {task}

-- 1. 激活应用
tell application "目标应用"
    activate
end tell

delay 1

-- 2. 执行操作
tell application "System Events"
    tell process "目标应用"
        -- 添加具体操作
    end tell
end tell
'''
        
        return ToolResult(
            success=True,
            data={
                "script": full_script,
                "suggestions": suggestions,
                "templates_used": len(script_parts),
                "note": "这是一个初始脚本框架，可能需要根据实际情况调整"
            }
        )
    
    async def _generate_python(self, kwargs: Dict[str, Any]) -> ToolResult:
        """生成 Python 脚本"""
        task = kwargs.get("task_description", "")
        
        if not task:
            return ToolResult(success=False, error="需要提供 task_description")
        
        # 基础 Python 脚本框架
        script = f'''#!/usr/bin/env python3
"""
自动生成的工具脚本
任务: {task}
生成时间: {datetime.now().isoformat()}
"""

import subprocess
import time

def run_applescript(script: str) -> str:
    """执行 AppleScript 并返回结果"""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def take_screenshot(region=None, output_path="/tmp/screenshot.png"):
    """截取屏幕截图"""
    cmd = ["screencapture"]
    if region:
        x, y, w, h = region
        cmd.extend(["-R", f"{{x}},{{y}},{{w}},{{h}}"])
    cmd.append(output_path)
    subprocess.run(cmd)
    return output_path

def main():
    # TODO: 根据任务实现具体逻辑
    pass

if __name__ == "__main__":
    main()
'''
        
        return ToolResult(
            success=True,
            data={
                "script": script,
                "note": "这是一个 Python 脚本框架，需要完善 main() 函数的实现"
            }
        )
    
    async def _test_script(self, kwargs: Dict[str, Any]) -> ToolResult:
        """测试脚本是否可用"""
        script = kwargs.get("script_content", "")
        script_type = kwargs.get("script_type", "applescript")
        
        if not script:
            return ToolResult(success=False, error="需要提供 script_content")
        
        try:
            if script_type == "applescript":
                process = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )
                
                if process.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=f"脚本执行失败: {stderr.decode()}",
                        data={"returncode": process.returncode}
                    )
                
                return ToolResult(
                    success=True,
                    data={
                        "output": stdout.decode(),
                        "script_type": script_type
                    }
                )
            
            elif script_type == "python":
                # 保存到临时文件并执行
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(script)
                    temp_path = f.name
                
                process = await asyncio.create_subprocess_exec(
                    "python3", temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=60
                )
                
                os.unlink(temp_path)
                
                if process.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=f"脚本执行失败: {stderr.decode()}",
                        data={"returncode": process.returncode}
                    )
                
                return ToolResult(
                    success=True,
                    data={
                        "output": stdout.decode(),
                        "script_type": script_type
                    }
                )
            
            elif script_type == "shell":
                process = await asyncio.create_subprocess_shell(
                    script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )
                
                return ToolResult(
                    success=process.returncode == 0,
                    data={
                        "output": stdout.decode(),
                        "stderr": stderr.decode(),
                        "returncode": process.returncode
                    }
                )
            
            else:
                return ToolResult(success=False, error=f"不支持的脚本类型: {script_type}")
                
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="脚本执行超时")
        except Exception as e:
            return ToolResult(success=False, error=f"执行异常: {str(e)}")
    
    async def _save_tool(self, kwargs: Dict[str, Any]) -> ToolResult:
        """保存脚本为可复用工具"""
        tool_name = kwargs.get("tool_name", "")
        script = kwargs.get("script_content", "")
        script_type = kwargs.get("script_type", "applescript")
        description = kwargs.get("task_description", "")
        
        if not tool_name or not script:
            return ToolResult(success=False, error="需要提供 tool_name 和 script_content")
        
        # 清理工具名称
        safe_name = "".join(c for c in tool_name if c.isalnum() or c in "_-")
        
        tool_data = {
            "name": safe_name,
            "description": description,
            "script_type": script_type,
            "script": script,
            "created_at": datetime.now().isoformat(),
            "usage_count": 0
        }
        
        # 保存到文件
        tool_path = os.path.join(GENERATED_TOOLS_DIR, f"{safe_name}.json")
        with open(tool_path, 'w', encoding='utf-8') as f:
            json.dump(tool_data, f, ensure_ascii=False, indent=2)
        
        return ToolResult(
            success=True,
            data={
                "saved_path": tool_path,
                "tool_name": safe_name,
                "message": f"工具 '{safe_name}' 已保存，可以使用 run_saved_tool 运行"
            }
        )
    
    async def _list_tools(self) -> ToolResult:
        """列出所有已生成的工具"""
        tools = []
        
        if os.path.exists(GENERATED_TOOLS_DIR):
            for filename in os.listdir(GENERATED_TOOLS_DIR):
                if filename.endswith('.json'):
                    filepath = os.path.join(GENERATED_TOOLS_DIR, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            tool_data = json.load(f)
                            tools.append({
                                "name": tool_data.get("name"),
                                "description": tool_data.get("description"),
                                "script_type": tool_data.get("script_type"),
                                "created_at": tool_data.get("created_at"),
                                "usage_count": tool_data.get("usage_count", 0)
                            })
                    except Exception as e:
                        logger.error(f"Failed to load tool {filename}: {e}")
        
        return ToolResult(
            success=True,
            data={
                "tools": tools,
                "count": len(tools),
                "directory": GENERATED_TOOLS_DIR
            }
        )
    
    async def _run_saved_tool(self, kwargs: Dict[str, Any]) -> ToolResult:
        """运行已保存的工具"""
        tool_name = kwargs.get("tool_name", "")
        tool_args = kwargs.get("tool_args", {})
        
        if not tool_name:
            return ToolResult(success=False, error="需要提供 tool_name")
        
        # 查找工具
        tool_path = os.path.join(GENERATED_TOOLS_DIR, f"{tool_name}.json")
        if not os.path.exists(tool_path):
            return ToolResult(success=False, error=f"找不到工具: {tool_name}")
        
        try:
            with open(tool_path, 'r', encoding='utf-8') as f:
                tool_data = json.load(f)
            
            script = tool_data.get("script", "")
            script_type = tool_data.get("script_type", "applescript")
            
            # 替换参数占位符
            for key, value in tool_args.items():
                script = script.replace(f"{{{key}}}", str(value))
            
            # 执行脚本
            result = await self._test_script({
                "script_content": script,
                "script_type": script_type
            })
            
            # 更新使用计数
            tool_data["usage_count"] = tool_data.get("usage_count", 0) + 1
            with open(tool_path, 'w', encoding='utf-8') as f:
                json.dump(tool_data, f, ensure_ascii=False, indent=2)
            
            return result
            
        except Exception as e:
            return ToolResult(success=False, error=f"运行工具失败: {str(e)}")


class GUIAutomationTool(BaseTool):
    """
    GUI 自动化工具 - 控制 macOS 应用程序界面
    """
    
    name = "gui_automation"
    description = """【必须优先使用】macOS GUI 操作的主工具 — 查找和操作应用程序的窗口、按钮、输入框等 UI 元素。
内部自动降级：AX 原生 API → OCR 视觉定位 → AppleScript，无需手动处理。

⚠️ 点击必须用 click_element（不要用 input_control mouse_click），输入文字必须用 type_text（不要用 input_control keyboard_type）。

核心操作（按顺序使用）：
1. get_gui_state → 获取应用界面状态（窗口数、焦点元素）
2. find_elements → 按名称查找 UI 元素（element_name 参数）
3. click_element → 点击找到的元素（element_name 参数，无需指定坐标）
4. type_text → 在焦点元素中输入文本（text 参数，使用 AXSetValue 原生输入）

典型流程: get_gui_state → find_elements("搜索") → click_element("搜索") → type_text("内容")

辅助操作：batch(批量)、get_window_info、get_ui_elements、click_position(仅 OCR fallback)"""
    
    category = ToolCategory.APPLICATION
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_window_info", "get_ui_elements", "click_element", 
                        "click_position", "type_text", "screenshot_window", "screenshot_region",
                        "get_gui_state", "find_elements", "batch"],
                "description": "要执行的操作"
            },
            "app_name": {
                "type": "string",
                "description": "应用程序名称"
            },
            "element_name": {
                "type": "string",
                "description": "UI 元素名称"
            },
            "element_type": {
                "type": "string",
                "description": "UI 元素类型（button, text field 等）"
            },
            "x": {
                "type": "number",
                "description": "X 坐标"
            },
            "y": {
                "type": "number",
                "description": "Y 坐标"
            },
            "width": {
                "type": "number",
                "description": "宽度"
            },
            "height": {
                "type": "number",
                "description": "高度"
            },
            "text": {
                "type": "string",
                "description": "要输入的文本"
            },
            "save_path": {
                "type": "string",
                "description": "截图保存路径"
            },
            "role": {
                "type": "string",
                "description": "UI 元素的 AX Role (如 AXButton, AXTextField)"
            },
            "title": {
                "type": "string",
                "description": "UI 元素标题或标签"
            },
            "batch_actions": {
                "type": "array",
                "description": "批量操作列表 [{\"actionType\": \"focus_app\", \"parameters\": {...}}, ...]",
                "items": {"type": "object"}
            },
            "atomic": {
                "type": "boolean",
                "description": "批量操作是否为原子事务（默认 true）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        app_name = kwargs.get("app_name", "")
        
        if action == "get_window_info":
            return await self._get_window_info(app_name)
        elif action == "get_ui_elements":
            return await self._get_ui_elements(app_name)
        elif action == "click_element":
            return await self._click_element(app_name, kwargs)
        elif action == "click_position":
            return await self._click_position(kwargs.get("x"), kwargs.get("y"))
        elif action == "type_text":
            return await self._type_text(app_name, kwargs.get("text", ""))
        elif action == "screenshot_window":
            return await self._screenshot_window(app_name, kwargs.get("save_path"))
        elif action == "screenshot_region":
            return await self._screenshot_region(kwargs)
        elif action == "get_gui_state":
            return await self._get_gui_state(app_name)
        elif action == "find_elements":
            return await self._find_elements(app_name, kwargs)
        elif action == "batch":
            return await self._execute_batch(kwargs)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _run_applescript(self, script: str) -> tuple:
        """执行 AppleScript"""
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()
    
    async def _get_window_info(self, app_name: str) -> ToolResult:
        """获取应用窗口信息 — 优先 IPC → Swift Bridge → pyobjc AX → AppleScript"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
        # ---- 1) 优先使用 IPC (Swift 端执行) ----
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            windows = await client.query_windows(app_name)
            if windows is not None:
                return ToolResult(success=True, data={"windows": windows, "source": "ipc"})
        except Exception as e:
            logger.debug("IPC get_window_info 失败: %s", e)
        
        # ---- 2) 尝试 Swift Bridge (HTTP) ----
        try:
            from runtime.accessibility_bridge_client import get_windows
            windows = await get_windows(app_name)
            if windows:
                return ToolResult(success=True, data={"windows": windows, "source": "swift_bridge"})
        except Exception as e:
            logger.debug("Swift Bridge get_window_info 失败: %s", e)
        
        # ---- 3) 尝试 pyobjc 原生 AX ----
        try:
            from runtime.ax_utils import HAS_AX, get_pid_for_app, get_app_element, get_element_info
            if HAS_AX:
                from runtime.ax_utils import _ax_get_attr
                pid = get_pid_for_app(app_name)
                if pid:
                    ax_app = get_app_element(pid)
                    ok, windows = _ax_get_attr(ax_app, "AXWindows")
                    if ok and windows:
                        result_windows = []
                        for w in windows:
                            winfo = get_element_info(w)
                            result_windows.append(winfo)
                        return ToolResult(success=True, data={"windows": result_windows, "source": "pyobjc_ax"})
        except Exception as e:
            logger.debug("pyobjc AX get_window_info 失败: %s", e)
        
        # ---- 3) AppleScript 回退 ----
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        if (count of windows) > 0 then
            set w to window 1
            set winName to name of w
            set winPos to position of w
            set winSize to size of w
            return "name:" & winName & "|pos:" & (item 1 of winPos) & "," & (item 2 of winPos) & "|size:" & (item 1 of winSize) & "," & (item 2 of winSize)
        else
            return "no_window"
        end if
    end tell
end tell
'''
        code, stdout, stderr = await self._run_applescript(script)
        if code != 0:
            return ToolResult(success=False, error=f"获取窗口信息失败: {stderr}")
        if stdout.strip() == "no_window":
            return ToolResult(success=False, error=f"应用 {app_name} 没有打开的窗口")
        parts = stdout.strip().split("|")
        info = {}
        for part in parts:
            if ":" in part:
                key, value = part.split(":", 1)
                if key == "pos" or key == "size":
                    x, y = value.split(",")
                    info[key] = {"x": int(x), "y": int(y)} if key == "pos" else {"width": int(x), "height": int(y)}
                else:
                    info[key] = value
        info["source"] = "applescript"
        return ToolResult(success=True, data=info)
    
    async def _get_ui_elements(self, app_name: str) -> ToolResult:
        """获取窗口内的 UI 元素 — 优先 IPC → Swift Bridge → pyobjc AX → AppleScript"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
        # ---- 1) 优先使用 IPC (Swift 端执行) ----
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            result = await client.query_elements(app_name, max_depth=5)
            if result is not None:
                return ToolResult(success=True, data={
                    "elements": result.get("elements", [])[:100],
                    "total_count": result.get("total", 0),
                    "source": "ipc"
                })
        except Exception as e:
            logger.debug("IPC get_ui_elements 失败: %s", e)
        
        # ---- 2) 尝试 Swift Bridge (HTTP) ----
        try:
            from runtime.accessibility_bridge_client import get_flat_elements
            elements, total = await get_flat_elements(app_name, max_depth=5, max_count=200)
            if elements:
                return ToolResult(success=True, data={
                    "elements": elements[:100],
                    "total_count": total,
                    "source": "swift_bridge"
                })
        except Exception as e:
            logger.debug("Swift Bridge get_ui_elements 失败: %s", e)
        
        # ---- 3) 尝试 pyobjc 原生 AX ----
        try:
            from runtime.ax_utils import HAS_AX, get_pid_for_app, get_app_element, find_elements as ax_find
            if HAS_AX:
                pid = get_pid_for_app(app_name)
                if pid:
                    ax_app = get_app_element(pid)
                    elements = ax_find(ax_app, max_depth=5, max_results=200)
                    clean = []
                    for e in elements:
                        entry = {k: v for k, v in e.items() if not k.startswith("_")}
                        clean.append(entry)
                    return ToolResult(success=True, data={
                        "elements": clean[:100],
                        "total_count": len(clean),
                        "source": "pyobjc_ax"
                    })
        except Exception as e:
            logger.debug("pyobjc AX get_ui_elements 失败: %s", e)
        
        # ---- 3) AppleScript 回退 ----
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        set uiList to {{}}
        try
            set allElements to entire contents of window 1
            repeat with elem in allElements
                try
                    set elemClass to class of elem as string
                    set elemName to ""
                    try
                        set elemName to name of elem
                    end try
                    if elemName is not "" then
                        set end of uiList to elemClass & ":" & elemName
                    end if
                end try
            end repeat
        end try
        return uiList as string
    end tell
end tell
'''
        code, stdout, stderr = await self._run_applescript(script)
        if code != 0:
            return ToolResult(success=False, error=f"获取 UI 元素失败: {stderr}")
        elements = []
        for item in stdout.strip().split(", "):
            if ":" in item:
                elem_type, elem_name = item.split(":", 1)
                elements.append({"type": elem_type, "name": elem_name})
        return ToolResult(success=True, data={
            "elements": elements[:50],
            "total_count": len(elements),
            "source": "applescript"
        })
    
    async def _click_element(self, app_name: str, kwargs: Dict[str, Any]) -> ToolResult:
        """点击指定元素 — 优先 IPC → Swift Bridge → pyobjc AX → AppleScript → TuriX → OCR"""
        element_name = kwargs.get("element_name", "")
        element_type = kwargs.get("element_type", "")
        
        if not app_name or not element_name:
            return ToolResult(success=False, error="需要提供 app_name 和 element_name")

        # 检查是否强制使用 TuriX 视觉模式（跳过 AX）
        force_vision = False
        try:
            from config.agent_config import load_agent_config
            force_vision = bool(load_agent_config().get("turix_force_vision", False))
        except Exception:
            pass
        if force_vision:
            return await self._click_element_vision(app_name, element_name)
        
        type_to_role = {
            "button": "AXButton", "text field": "AXTextField", "checkbox": "AXCheckBox",
            "radio button": "AXRadioButton", "menu item": "AXMenuItem",
            "static text": "AXStaticText", "link": "AXLink",
        }
        ax_role = type_to_role.get(element_type.lower(), None)
        
        # ---- 1) 优先使用 IPC (Swift 端执行) ----
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            await client.ensure_subscribed()  # 在点击前确保已订阅事件
            ok = await client.click_element(app_name, role=ax_role, title=element_name)
            if ok:
                # 等待 AX 事件确认（焦点变化/值变化），500ms 超时
                event = await client.wait_for_ax_event(
                    event_types=["AXFocusedUIElementChanged", "AXFocusedWindowChanged"],
                    app_name=app_name,
                    timeout_ms=500,
                )
                result_data = {"clicked": element_name, "source": "ipc"}
                if event:
                    result_data["ax_event_confirmed"] = event.get("eventType", "")
                    result_data["new_focus"] = event.get("payload", {}).get("element_title", "")
                else:
                    # AXPress 事件超时 — 通过 AX 树坐标做 CGEvent 补充点击
                    logger.debug("click_element: AXPress 事件超时，尝试 AX 坐标 fallback")
                    elements = await client.find_elements(app_name, role=ax_role, title=element_name, max_count=5)
                    if elements:
                        for elem in elements:
                            cx = elem.get("center_x") or elem.get("x")
                            cy = elem.get("center_y") or elem.get("y")
                            if cx and cy:
                                await client.click_position(float(cx), float(cy))
                                result_data["source"] = "ipc_ax_coordinate"
                                result_data["click_position"] = {"x": cx, "y": cy}
                                break
                    result_data["ax_event_confirmed"] = None
                return ToolResult(success=True, data=result_data)
        except Exception as e:
            logger.debug("IPC click_element 失败: %s", e)
        
        # ---- 2) 尝试 Swift Bridge (HTTP) ----
        try:
            from runtime.accessibility_bridge_client import perform_action
            ok, err = await perform_action(app_name, role=ax_role, title=element_name)
            if ok:
                return ToolResult(success=True, data={"clicked": element_name, "source": "swift_bridge"})
            logger.debug("Swift Bridge click_element 失败: %s", err)
        except Exception as e:
            logger.debug("Swift Bridge click_element 异常: %s", e)
        
        # ---- 3) 尝试 pyobjc 原生 AX ----
        try:
            from runtime.ax_utils import HAS_AX, get_pid_for_app, find_and_click
            if HAS_AX:
                pid = get_pid_for_app(app_name)
                if pid:
                    ok, err = find_and_click(pid, role=ax_role or "AXButton", title=element_name)
                    if ok:
                        return ToolResult(success=True, data={"clicked": element_name, "source": "pyobjc_ax"})
                    logger.debug("pyobjc click_element 失败: %s", err)
        except Exception as e:
            logger.debug("pyobjc AX click_element 异常: %s", e)
        
        # ---- 4) AppleScript 回退 ----
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        try
            click {element_type} "{element_name}" of window 1
            return "success"
        on error errMsg
            return "error:" & errMsg
        end try
    end tell
end tell
'''
        code, stdout, stderr = await self._run_applescript(script)
        if not stdout.startswith("error:"):
            return ToolResult(success=True, data={"clicked": element_name, "source": "applescript"})

        # ---- 5) TuriX Actor 视觉定位（VLM 精准坐标预测） ----
        try:
            from runtime.turix_actor import get_turix_actor
            turix = get_turix_actor()
            if turix.is_available():
                result = await turix.locate_element(element_name)
                if result.get("found"):
                    click_result = await self._click_position(result["x"], result["y"])
                    if click_result.success:
                        click_result.data["source"] = "turix_actor"
                        click_result.data["raw_coords"] = result.get("raw_coords")
                        return click_result
        except Exception as e:
            logger.debug("TuriX Actor click_element 降级失败: %s", e)

        # ---- 6) PaddleOCR 视觉降级：截屏 → OCR 定位 → 坐标点击 ----
        try:
            from runtime.paddle_ocr import is_available as ocr_available, run_paddle_ocr, resolve_target
            if ocr_available():
                import subprocess
                screenshot_path = f"/tmp/gui_click_{int(datetime.now().timestamp())}.png"
                subprocess.run(["screencapture", "-x", "-C", screenshot_path], check=True, timeout=5)
                layout = await run_paddle_ocr(screenshot_path, preprocess=False)
                if layout and layout.items:
                    match = resolve_target(layout, element_name)
                    if match and match.score >= 0.4:
                        click_result = await self._click_position(match.item.center_x, match.item.center_y)
                        if click_result.success:
                            click_result.data["source"] = "paddleocr_vision"
                            click_result.data["matched_text"] = match.item.text
                            click_result.data["match_score"] = round(match.score, 2)
                            return click_result
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass
        except Exception as e:
            logger.debug("PaddleOCR click_element 降级失败: %s", e)

        return ToolResult(success=False, error=f"无法点击元素 '{element_name}'：AX 和视觉定位均失败")

    async def _click_element_vision(self, app_name: str, element_name: str) -> ToolResult:
        """纯视觉模式点击 — 仅使用 TuriX Actor + PaddleOCR（跳过 AX）"""
        # TuriX Actor
        try:
            from runtime.turix_actor import get_turix_actor
            turix = get_turix_actor()
            if turix.is_available():
                result = await turix.locate_element(element_name)
                if result.get("found"):
                    click_result = await self._click_position(result["x"], result["y"])
                    if click_result.success:
                        click_result.data["source"] = "turix_actor"
                        click_result.data["raw_coords"] = result.get("raw_coords")
                        return click_result
                logger.debug("TuriX Actor 未找到 '%s': %s", element_name, result.get("error", ""))
        except Exception as e:
            logger.debug("TuriX Actor click_element_vision 异常: %s", e)

        # PaddleOCR fallback
        try:
            from runtime.paddle_ocr import is_available as ocr_available, run_paddle_ocr, resolve_target
            if ocr_available():
                import subprocess
                screenshot_path = f"/tmp/gui_click_v_{int(datetime.now().timestamp())}.png"
                subprocess.run(["screencapture", "-x", "-C", screenshot_path], check=True, timeout=5)
                layout = await run_paddle_ocr(screenshot_path, preprocess=False)
                if layout and layout.items:
                    match = resolve_target(layout, element_name)
                    if match and match.score >= 0.4:
                        click_result = await self._click_position(match.item.center_x, match.item.center_y)
                        if click_result.success:
                            click_result.data["source"] = "paddleocr_vision"
                            return click_result
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass
        except Exception as e:
            logger.debug("PaddleOCR click_element_vision 异常: %s", e)

        return ToolResult(success=False, error=f"视觉模式无法点击 '{element_name}'")
    
    async def _click_position(self, x: float, y: float) -> ToolResult:
        """点击指定坐标 — 优先 IPC → CGEvent → cliclick"""
        if x is None or y is None:
            return ToolResult(success=False, error="需要提供 x 和 y 坐标")
        
        ix, iy = int(x), int(y)

        # ---- 1) 优先使用 IPC (Swift 端 CGEvent) ----
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            ok = await client.click_position(float(ix), float(iy))
            if ok:
                return ToolResult(success=True, data={"clicked_at": {"x": ix, "y": iy}, "source": "ipc"})
        except Exception as e:
            logger.debug("IPC click_position 失败: %s", e)

        # ---- 2) 进程内 CGEvent ----
        try:
            from runtime import cg_event as _cg
            if _cg.HAS_QUARTZ:
                ok, err = _cg.mouse_click(ix, iy, button="left", clicks=1)
                if ok:
                    return ToolResult(success=True, data={"clicked_at": {"x": ix, "y": iy}})
                logger.warning("CGEvent click_position 失败: %s", err)
        except Exception:
            pass

        # 回退: cliclick
        try:
            process = await asyncio.create_subprocess_exec(
                "cliclick", f"c:{ix},{iy}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode == 0:
                return ToolResult(success=True, data={"clicked_at": {"x": ix, "y": iy}})
        except FileNotFoundError:
            pass

        # 最终回退: AppleScript（通过 cliclick 风格不可用时用 osascript 模拟）
        script = f'''
do shell script "cliclick c:{ix},{iy}" 
'''
        code, stdout, stderr = await self._run_applescript(script)
        if code == 0:
            return ToolResult(success=True, data={"clicked_at": {"x": ix, "y": iy}})

        return ToolResult(success=False, error=f"点击 ({ix}, {iy}) 失败：CGEvent 和 cliclick 均不可用。{stderr}")
    
    async def _type_text(self, app_name: str, text: str) -> ToolResult:
        """输入文本 — 优先 IPC → Swift Bridge → pyobjc AX → CGEvent → AppleScript"""
        if not text:
            return ToolResult(success=False, error="需要提供 text")
        
        # ---- 1) 优先使用 IPC (Swift 端输入) ----
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            # 如果有 app_name，先尝试 set_value (AXSetValue 原生)
            if app_name:
                await client.ensure_subscribed()  # 在输入前确保已订阅事件
                ok = await client.set_value(app_name, text, role="AXTextField")
                if ok:
                    # 等待 AXValueChanged 事件确认
                    event = await client.wait_for_ax_event(
                        event_types=["AXValueChanged", "AXSelectedTextChanged"],
                        app_name=app_name,
                        timeout_ms=500,
                    )
                    result_data = {"typed": text, "source": "ipc_set_value"}
                    if event:
                        result_data["ax_event_confirmed"] = event.get("eventType", "")
                    return ToolResult(success=True, data=result_data)
            # 回退到键盘输入
            ok = await client.type_text(text)
            if ok:
                return ToolResult(success=True, data={"typed": text, "source": "ipc_key_press"})
        except Exception as e:
            logger.debug("IPC type_text 失败: %s", e)
        
        # ---- 2) 尝试 pyobjc 原生 AX：设置焦点元素的值 ----
        if app_name:
            try:
                from runtime.ax_utils import HAS_AX, get_pid_for_app, get_app_element, get_focused_element, set_element_value
                if HAS_AX:
                    pid = get_pid_for_app(app_name)
                    if pid:
                        ax_app = get_app_element(pid)
                        focused = get_focused_element(ax_app)
                        if focused:
                            ok, err = set_element_value(focused, text)
                            if ok:
                                return ToolResult(success=True, data={"typed": text, "source": "pyobjc_ax"})
            except Exception as e:
                logger.debug("pyobjc AX type_text 失败: %s", e)
            
            # ---- 2) 尝试 Swift Bridge: set-value 到焦点元素 ----
            try:
                from runtime.accessibility_bridge_client import set_value
                ok, err = await set_value(app_name, value=text, role="AXTextField")
                if ok:
                    return ToolResult(success=True, data={"typed": text, "source": "swift_bridge"})
            except Exception as e:
                logger.debug("Swift Bridge type_text 失败: %s", e)
        
        # ---- 3) CGEvent 键盘输入 ----
        try:
            from runtime.cg_event import HAS_QUARTZ, type_text as cg_type_text
            if HAS_QUARTZ:
                ok, err = await cg_type_text(text)
                if ok:
                    return ToolResult(success=True, data={"typed": text, "source": "cg_event"})
        except Exception:
            pass
        
        # ---- 4) AppleScript 回退 ----
        # 安全地对文本中的特殊字符进行转义
        safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'''
tell application "System Events"
    keystroke "{safe_text}"
end tell
'''
        code, stdout, stderr = await self._run_applescript(script)
        if code != 0:
            return ToolResult(success=False, error=f"输入文本失败: {stderr}")
        return ToolResult(success=True, data={"typed": text, "source": "applescript"})
    
    async def _screenshot_window(self, app_name: str, save_path: Optional[str]) -> ToolResult:
        """截取应用窗口（自动，无需用户交互）"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
        # 首先激活窗口
        activate_script = f'''
tell application "{app_name}"
    activate
end tell
'''
        await self._run_applescript(activate_script)
        await asyncio.sleep(0.5)
        
        if not save_path:
            save_path = f"/tmp/window_{int(datetime.now().timestamp())}.png"
        
        # 获取窗口 ID 并自动截图（无需用户交互）
        window_id = await self._get_window_id(app_name)
        if window_id:
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-l", str(window_id), save_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        else:
            # 备用方案：使用窗口边界
            bounds = await self._get_window_bounds(app_name)
            if bounds:
                x, y, w, h = bounds
                region = f"{int(x)},{int(y)},{int(w)},{int(h)}"
                process = await asyncio.create_subprocess_exec(
                    "screencapture", "-x", "-R", region, save_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
            else:
                return ToolResult(success=False, error=f"无法获取 {app_name} 窗口信息")
        
        if os.path.exists(save_path):
            # 读取图片并转为 base64，以便在聊天窗口显示
            image_base64 = None
            try:
                with open(save_path, "rb") as f:
                    import base64
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
            
            result_data = {
                "screenshot_path": save_path,
                "path": save_path,
                "size": os.path.getsize(save_path),
                "app_name": app_name
            }
            
            if image_base64:
                result_data["image_base64"] = image_base64
                result_data["mime_type"] = "image/png"
            
            return ToolResult(success=True, data=result_data)
        else:
            return ToolResult(success=False, error="截图失败")
    
    async def _get_window_id(self, app_name: str) -> Optional[int]:
        """获取应用窗口 ID"""
        py_script = f'''
import Quartz
import sys

windows = Quartz.CGWindowListCopyWindowInfo(
    Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
    Quartz.kCGNullWindowID
)

for window in windows:
    owner = window.get(Quartz.kCGWindowOwnerName, "")
    if "{app_name}" in owner or owner == "{app_name}":
        layer = window.get(Quartz.kCGWindowLayer, 0)
        if layer == 0:
            print(window.get(Quartz.kCGWindowNumber, 0))
            sys.exit(0)
print(0)
'''
        try:
            process = await asyncio.create_subprocess_exec(
                "python3", "-c", py_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            window_id = int(stdout.decode().strip())
            if window_id > 0:
                return window_id
        except Exception:
            pass
        return None
    
    async def _get_window_bounds(self, app_name: str) -> Optional[tuple]:
        """获取应用窗口边界"""
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        if (count of windows) > 0 then
            set w to window 1
            set pos to position of w
            set sz to size of w
            return (item 1 of pos) & "," & (item 2 of pos) & "," & (item 1 of sz) & "," & (item 2 of sz)
        end if
    end tell
end tell
'''
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                output = stdout.decode().strip()
                parts = output.split(",")
                if len(parts) == 4:
                    return tuple(int(p.strip()) for p in parts)
        except Exception:
            pass
        return None
    
    async def _screenshot_region(self, kwargs: Dict[str, Any]) -> ToolResult:
        """截取指定区域"""
        x = kwargs.get("x")
        y = kwargs.get("y")
        width = kwargs.get("width")
        height = kwargs.get("height")
        save_path = kwargs.get("save_path")
        
        if None in (x, y, width, height):
            return ToolResult(success=False, error="需要提供 x, y, width, height")
        
        if not save_path:
            save_path = f"/tmp/region_{int(datetime.now().timestamp())}.png"
        
        # 使用 screencapture -R 截取指定区域（-x 静默模式）
        region = f"{int(x)},{int(y)},{int(width)},{int(height)}"
        
        process = await asyncio.create_subprocess_exec(
            "screencapture", "-x", "-R", region, save_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(save_path):
            # 读取图片并转为 base64，以便在聊天窗口显示
            image_base64 = None
            try:
                with open(save_path, "rb") as f:
                    import base64
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
            
            result_data = {
                "screenshot_path": save_path,
                "path": save_path,
                "region": {"x": x, "y": y, "width": width, "height": height},
                "size": os.path.getsize(save_path)
            }
            
            if image_base64:
                result_data["image_base64"] = image_base64
                result_data["mime_type"] = "image/png"
            
            return ToolResult(success=True, data=result_data)
        else:
            return ToolResult(success=False, error="截图失败")
    
    async def _get_gui_state(self, app_name: str = "") -> ToolResult:
        """获取 GUI 状态 — 针对目标应用返回窗口数、焦点信息、UI 元素摘要"""
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            await client.ensure_subscribed()

            result: Dict[str, Any] = {}

            # 如果指定了 app_name，返回该应用的具体信息
            if app_name:
                # 获取应用窗口信息
                windows = await client.query_windows(app_name)
                result["app_name"] = app_name
                result["window_count"] = len(windows) if windows else 0
                result["windows"] = windows[:5] if windows else []

                # 获取前 20 个 UI 元素摘要
                elements = await client.find_elements(app_name, max_count=20)
                if elements:
                    result["ui_elements_sample"] = [
                        {k: v for k, v in e.items() if k in ("title", "role", "value", "enabled")}
                        for e in elements[:20]
                    ]
                    result["total_elements"] = len(elements)

                return ToolResult(success=True, data=result)

            # 无 app_name 时返回全局焦点信息
            focused = await client.query_focused()
            if focused:
                result["focused"] = focused
            state = await client.query_state()
            if state:
                result.update(state)
            return ToolResult(success=True, data=result) if result else ToolResult(success=False, error="无法获取 GUI 状态")
        except Exception as e:
            logger.debug("IPC get_gui_state 失败: %s", e)
        return ToolResult(success=False, error="IPC 不可用，无法获取 GUI 状态")
    
    async def _find_elements(self, app_name: str, kwargs: Dict[str, Any]) -> ToolResult:
        """按条件搜索 UI 元素 — AX 优先，自动降级 TuriX / PaddleOCR 视觉定位"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        role = kwargs.get("role")
        title = kwargs.get("title") or kwargs.get("element_name")

        # 检查是否强制使用 TuriX 视觉模式
        force_vision = False
        try:
            from config.agent_config import load_agent_config
            force_vision = bool(load_agent_config().get("turix_force_vision", False))
        except Exception:
            pass
        if force_vision and title:
            return await self._find_elements_vision(title)

        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            elements = await client.find_elements(app_name, role=role, title=title)
            if elements is not None and len(elements) > 0:
                return ToolResult(success=True, data={"elements": elements, "count": len(elements), "source": "ipc"})
        except Exception as e:
            logger.debug("IPC find_elements 失败: %s", e)

        # AX 降级：全量 UI 元素
        ax_result = await self._get_ui_elements(app_name)
        if ax_result.success and title:
            # 在 AX 结果中按名称过滤
            elems = ax_result.data.get("elements", [])
            matched = [e for e in elems if title.lower() in str(e.get("name", "")).lower() or title.lower() in str(e.get("title", "")).lower()]
            if matched:
                return ToolResult(success=True, data={"elements": matched, "count": len(matched), "source": ax_result.data.get("source", "ax")})

        # ---- TuriX Actor 视觉定位（VLM fallback） ----
        if title:
            try:
                from runtime.turix_actor import get_turix_actor
                turix = get_turix_actor()
                if turix.is_available():
                    turix_elements = await turix.find_elements(title)
                    if turix_elements:
                        return ToolResult(success=True, data={
                            "elements": turix_elements,
                            "count": len(turix_elements),
                            "source": "turix_actor",
                        })
            except Exception as e:
                logger.debug("TuriX Actor find_elements 降级失败: %s", e)

        # ---- PaddleOCR 视觉降级（AX 找不到时自动截屏 + OCR 定位） ----
        if title:
            try:
                from runtime.paddle_ocr import is_available as ocr_available, run_paddle_ocr, resolve_target, find_all_matches
                if ocr_available():
                    import subprocess, tempfile
                    screenshot_path = f"/tmp/gui_find_{int(datetime.now().timestamp())}.png"
                    subprocess.run(["screencapture", "-x", "-C", screenshot_path], check=True, timeout=5)
                    layout = await run_paddle_ocr(screenshot_path, preprocess=False)
                    if layout and layout.items:
                        matches = find_all_matches(layout, title, min_score=0.4)
                        if matches:
                            elements = []
                            for m in matches[:10]:
                                elements.append({
                                    "name": m.item.text,
                                    "role": "OCRText",
                                    "center": {"x": int(m.item.center_x), "y": int(m.item.center_y)},
                                    "bbox": [int(v) for v in m.item.bbox],
                                    "confidence": round(m.item.confidence, 2),
                                    "match_score": round(m.score, 2),
                                    "match_method": m.method,
                                })
                            return ToolResult(success=True, data={
                                "elements": elements,
                                "count": len(elements),
                                "source": "paddleocr_vision",
                                "hint": "元素通过 OCR 视觉定位，可用 center 坐标进行 click_position"
                            })
                    # 清理
                    try:
                        os.remove(screenshot_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.debug("PaddleOCR find_elements 降级失败: %s", e)

        return ax_result

    async def _find_elements_vision(self, title: str) -> ToolResult:
        """纯视觉模式查找元素 — 仅使用 TuriX Actor + PaddleOCR"""
        # TuriX Actor
        try:
            from runtime.turix_actor import get_turix_actor
            turix = get_turix_actor()
            if turix.is_available():
                elements = await turix.find_elements(title)
                if elements:
                    return ToolResult(success=True, data={
                        "elements": elements,
                        "count": len(elements),
                        "source": "turix_actor",
                    })
        except Exception as e:
            logger.debug("TuriX Actor find_elements_vision 异常: %s", e)

        # PaddleOCR fallback
        try:
            from runtime.paddle_ocr import is_available as ocr_available, run_paddle_ocr, find_all_matches
            if ocr_available():
                import subprocess
                screenshot_path = f"/tmp/gui_find_v_{int(datetime.now().timestamp())}.png"
                subprocess.run(["screencapture", "-x", "-C", screenshot_path], check=True, timeout=5)
                layout = await run_paddle_ocr(screenshot_path, preprocess=False)
                if layout and layout.items:
                    matches = find_all_matches(layout, title, min_score=0.4)
                    if matches:
                        elements = [{
                            "name": m.item.text,
                            "role": "OCRText",
                            "center": {"x": int(m.item.center_x), "y": int(m.item.center_y)},
                            "confidence": round(m.item.confidence, 2),
                            "source": "paddleocr_vision",
                        } for m in matches[:10]]
                        return ToolResult(success=True, data={"elements": elements, "count": len(elements), "source": "paddleocr_vision"})
                try:
                    os.remove(screenshot_path)
                except OSError:
                    pass
        except Exception as e:
            logger.debug("PaddleOCR find_elements_vision 异常: %s", e)

        return ToolResult(success=False, error=f"视觉模式未找到 '{title}'")
    
    async def _execute_batch(self, kwargs: Dict[str, Any]) -> ToolResult:
        """批量执行多个 GUI 操作（原子事务）"""
        actions = kwargs.get("batch_actions", [])
        atomic = kwargs.get("atomic", True)
        if not actions:
            return ToolResult(success=False, error="需要提供 batch_actions")
        try:
            from runtime.ipc_client import get_ipc_client
            client = get_ipc_client()
            result = await client.execute_batch(actions, atomic=atomic)
            if result is not None:
                return ToolResult(success=True, data=result)
        except Exception as e:
            logger.debug("IPC batch 失败: %s", e)
        return ToolResult(success=False, error="IPC 不可用，无法执行批量操作")
