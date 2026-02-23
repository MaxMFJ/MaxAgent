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
    description = """GUI 自动化工具，用于控制 macOS 应用程序界面。

支持的操作：
- get_window_info: 获取应用窗口信息（位置、大小）
- get_ui_elements: 获取窗口内的 UI 元素列表
- click_element: 点击指定元素
- click_position: 点击指定坐标
- type_text: 输入文本
- screenshot_window: 截取应用窗口
- screenshot_region: 截取指定区域

使用场景：
- 控制特定应用的界面
- 自动化 GUI 操作
- 截取应用特定区域"""
    
    category = ToolCategory.APPLICATION
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_window_info", "get_ui_elements", "click_element", 
                        "click_position", "type_text", "screenshot_window", "screenshot_region"],
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
        """获取应用窗口信息"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
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
        
        # 解析输出
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
        
        return ToolResult(success=True, data=info)
    
    async def _get_ui_elements(self, app_name: str) -> ToolResult:
        """获取窗口内的 UI 元素"""
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
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
        
        # 解析元素列表
        elements = []
        for item in stdout.strip().split(", "):
            if ":" in item:
                elem_type, elem_name = item.split(":", 1)
                elements.append({"type": elem_type, "name": elem_name})
        
        return ToolResult(
            success=True,
            data={
                "elements": elements[:50],  # 限制返回数量
                "total_count": len(elements)
            }
        )
    
    async def _click_element(self, app_name: str, kwargs: Dict[str, Any]) -> ToolResult:
        """点击指定元素"""
        element_name = kwargs.get("element_name", "")
        element_type = kwargs.get("element_type", "button")
        
        if not app_name or not element_name:
            return ToolResult(success=False, error="需要提供 app_name 和 element_name")
        
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
        
        if stdout.startswith("error:"):
            return ToolResult(success=False, error=stdout)
        
        return ToolResult(success=True, data={"clicked": element_name})
    
    async def _click_position(self, x: float, y: float) -> ToolResult:
        """点击指定坐标"""
        if x is None or y is None:
            return ToolResult(success=False, error="需要提供 x 和 y 坐标")
        
        # 使用 cliclick 或 AppleScript
        script = f'''
tell application "System Events"
    click at {{{int(x)}, {int(y)}}}
end tell
'''
        
        code, stdout, stderr = await self._run_applescript(script)
        
        if code != 0:
            return ToolResult(success=False, error=f"点击失败: {stderr}")
        
        return ToolResult(success=True, data={"clicked_at": {"x": x, "y": y}})
    
    async def _type_text(self, app_name: str, text: str) -> ToolResult:
        """输入文本"""
        if not text:
            return ToolResult(success=False, error="需要提供 text")
        
        script = f'''
tell application "System Events"
    keystroke "{text}"
end tell
'''
        
        code, stdout, stderr = await self._run_applescript(script)
        
        if code != 0:
            return ToolResult(success=False, error=f"输入文本失败: {stderr}")
        
        return ToolResult(success=True, data={"typed": text})
    
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
            except:
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
        except:
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
        except:
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
            except:
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
