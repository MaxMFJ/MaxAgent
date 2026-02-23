"""
Vision Tool - 视觉理解工具
让 Agent 能够"看到"屏幕内容并理解
"""

import os
import base64
import asyncio
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)


class VisionTool(BaseTool):
    """
    视觉理解工具 - 让 Agent 能够看到并理解屏幕内容
    
    核心能力：
    1. 截取屏幕/窗口/区域
    2. 使用 OCR 识别文字
    3. 使用视觉模型理解图像内容
    4. 定位 UI 元素的位置
    """
    
    name = "vision"
    description = """视觉工具，用于截图、OCR、查找元素。截图会自动显示在聊天窗口中。

支持的操作：
- capture_and_analyze: 截图（使用 app_name 指定应用）
- find_element: 查找 UI 元素位置
- read_screen: 读取屏幕文字
- get_qrcode: 截图并识别二维码

使用 app_name 参数指定应用：WeChat、Safari、Finder 等

【重要】如果用户只是要截图，用 screenshot 工具更简单。截图完成后立即结束，不要做额外分析。"""
    
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["capture_and_analyze", "find_element", "read_screen", 
                        "describe_window", "get_qrcode"],
                "description": "要执行的操作"
            },
            "app_name": {
                "type": "string",
                "description": "应用程序名称"
            },
            "target": {
                "type": "string",
                "description": "要查找的目标元素描述"
            },
            "area": {
                "type": "string",
                "enum": ["full", "window", "region"],
                "description": "截图区域"
            },
            "region": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"}
                },
                "description": "截图区域（当 area=region 时使用）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        
        if action == "capture_and_analyze":
            return await self._capture_and_analyze(kwargs)
        elif action == "find_element":
            return await self._find_element(kwargs)
        elif action == "read_screen":
            return await self._read_screen(kwargs)
        elif action == "describe_window":
            return await self._describe_window(kwargs)
        elif action == "get_qrcode":
            return await self._get_qrcode(kwargs)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _capture_screenshot(self, area: str = "full", app_name: str = "", 
                                   region: Optional[Dict] = None) -> Optional[str]:
        """截取屏幕截图（自动，无需用户交互）"""
        timestamp = int(datetime.now().timestamp())
        save_path = f"/tmp/vision_{timestamp}.png"
        
        if app_name:
            # 使用窗口 ID 自动截取指定应用窗口（无需用户交互）
            # 先激活窗口
            activate_script = f'''
tell application "{app_name}"
    activate
end tell
'''
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", activate_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            await asyncio.sleep(0.5)
            
            # 获取窗口 ID 并自动截图
            window_id = await self._get_window_id(app_name)
            if window_id:
                process = await asyncio.create_subprocess_exec(
                    "screencapture", "-x", "-l", str(window_id), save_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                if os.path.exists(save_path):
                    return save_path
            
            # 备用方案：使用窗口边界截图
            bounds = await self._get_window_bounds(app_name)
            if bounds:
                x, y, w, h = bounds
                region_str = f"{int(x)},{int(y)},{int(w)},{int(h)}"
                process = await asyncio.create_subprocess_exec(
                    "screencapture", "-x", "-R", region_str, save_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                if os.path.exists(save_path):
                    return save_path
            
            # 最后备用：全屏截图
            logger.warning(f"无法获取 {app_name} 窗口，使用全屏截图")
            
        elif area == "region" and region:
            x, y, w, h = region.get("x"), region.get("y"), region.get("width"), region.get("height")
            region_str = f"{int(x)},{int(y)},{int(w)},{int(h)}"
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-R", region_str, save_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        else:
            # 全屏截图
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", save_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        
        if os.path.exists(save_path):
            return save_path
        return None
    
    async def _get_window_id(self, app_name: str) -> Optional[int]:
        """获取应用窗口的 ID"""
        try:
            import Quartz
            
            windows = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID
            )
            
            # 搜索名称匹配：支持中英文名称和别名
            app_name_lower = app_name.lower()
            
            # 常见应用的别名映射
            aliases = {
                "wechat": ["微信", "wechat", "企业微信"],
                "微信": ["微信", "wechat", "企业微信"],
                "safari": ["safari", "safari浏览器"],
                "chrome": ["chrome", "google chrome"],
                "vscode": ["code", "visual studio code"],
                "cursor": ["cursor"],
            }
            
            # 获取所有可能的匹配名称
            match_names = [app_name_lower]
            for key, values in aliases.items():
                if app_name_lower in key.lower() or key.lower() in app_name_lower:
                    match_names.extend([v.lower() for v in values])
            match_names = list(set(match_names))
            
            for window in windows:
                owner = window.get(Quartz.kCGWindowOwnerName, "")
                owner_lower = owner.lower()
                
                matched = False
                for match_name in match_names:
                    if match_name in owner_lower or owner_lower in match_name:
                        matched = True
                        break
                
                if matched:
                    layer = window.get(Quartz.kCGWindowLayer, 0)
                    if layer == 0:
                        window_id = window.get(Quartz.kCGWindowNumber, 0)
                        if window_id > 0:
                            logger.info(f"Got window ID for {app_name} (owner={owner}): {window_id}")
                            return window_id
            
            logger.warning(f"No window ID found for {app_name}")
            return None
            
        except ImportError:
            logger.warning("Quartz module not available")
            return None
        except Exception as e:
            logger.warning(f"获取窗口 ID 失败: {e}")
            return None
    
    async def _get_window_bounds(self, app_name: str) -> Optional[tuple]:
        """获取应用窗口的边界"""
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
        except Exception as e:
            logger.warning(f"获取窗口边界失败: {e}")
        
        return None
    
    async def _ocr_image(self, image_path: str) -> str:
        """使用 macOS Vision 框架进行 OCR"""
        swift_script = '''
import Cocoa
import Vision

let imagePath = CommandLine.arguments[1]

guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("ERROR: Cannot load image")
    exit(1)
}

let request = VNRecognizeTextRequest { request, error in
    guard let observations = request.results as? [VNRecognizedTextObservation] else {
        print("ERROR: No text found")
        exit(1)
    }
    
    let text = observations.compactMap { observation in
        observation.topCandidates(1).first?.string
    }.joined(separator: "\\n")
    
    print(text)
}

request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
'''
        
        script_path = "/tmp/ocr_script.swift"
        with open(script_path, "w") as f:
            f.write(swift_script)
        
        try:
            process = await asyncio.create_subprocess_exec(
                "swift", script_path, image_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            
            if process.returncode == 0:
                return stdout.decode().strip()
            else:
                # 尝试 tesseract
                process = await asyncio.create_subprocess_exec(
                    "tesseract", image_path, "stdout", "-l", "chi_sim+eng",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                return stdout.decode().strip()
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return ""
    
    async def _detect_qrcode(self, image_path: str) -> Optional[str]:
        """检测并解码二维码"""
        swift_script = '''
import Cocoa
import Vision

let imagePath = CommandLine.arguments[1]

guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("ERROR: Cannot load image")
    exit(1)
}

let request = VNDetectBarcodesRequest { request, error in
    guard let observations = request.results as? [VNBarcodeObservation] else {
        print("NO_QRCODE")
        exit(0)
    }
    
    for observation in observations {
        if let payload = observation.payloadStringValue {
            print("QRCODE:" + payload)
            print("BOUNDS:" + String(describing: observation.boundingBox))
        }
    }
}

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
'''
        
        script_path = "/tmp/qrcode_script.swift"
        with open(script_path, "w") as f:
            f.write(swift_script)
        
        try:
            process = await asyncio.create_subprocess_exec(
                "swift", script_path, image_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
            
            output = stdout.decode().strip()
            if "QRCODE:" in output:
                # 解析二维码内容
                for line in output.split("\n"):
                    if line.startswith("QRCODE:"):
                        return line[7:]
            return None
        except Exception as e:
            logger.error(f"QR code detection failed: {e}")
            return None
    
    async def _capture_and_analyze(self, kwargs: Dict[str, Any]) -> ToolResult:
        """截图并分析内容"""
        area = kwargs.get("area", "full")
        app_name = kwargs.get("app_name", "")
        region = kwargs.get("region")
        
        screenshot_path = await self._capture_screenshot(area, app_name, region)
        if not screenshot_path:
            return ToolResult(success=False, error="截图失败")
        
        # OCR 识别文字
        text = await self._ocr_image(screenshot_path)
        
        # 检测二维码
        qrcode = await self._detect_qrcode(screenshot_path)
        
        # 读取图片并编码为 base64（供前端显示）
        with open(screenshot_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()
        
        return ToolResult(
            success=True,
            data={
                "screenshot_path": screenshot_path,
                "image_base64": image_base64,
                "ocr_text": text,
                "has_qrcode": qrcode is not None,
                "qrcode_content": qrcode,
                "analysis": {
                    "text_length": len(text),
                    "has_chinese": any('\u4e00' <= c <= '\u9fff' for c in text)
                }
            }
        )
    
    async def _find_element(self, kwargs: Dict[str, Any]) -> ToolResult:
        """在截图中查找指定元素"""
        target = kwargs.get("target", "")
        app_name = kwargs.get("app_name", "")
        
        if not target:
            return ToolResult(success=False, error="需要提供 target 描述")
        
        # 首先通过 Accessibility API 尝试查找
        if app_name:
            script = f'''
tell application "System Events"
    tell process "{app_name}"
        set uiList to {{}}
        try
            set allElements to entire contents of window 1
            repeat with elem in allElements
                try
                    set elemName to name of elem
                    if elemName contains "{target}" then
                        set elemPos to position of elem
                        set elemSize to size of elem
                        set end of uiList to "FOUND:" & elemName & "|POS:" & (item 1 of elemPos) & "," & (item 2 of elemPos) & "|SIZE:" & (item 1 of elemSize) & "," & (item 2 of elemSize)
                    end if
                end try
            end repeat
        end try
        return uiList as string
    end tell
end tell
'''
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip()
            if "FOUND:" in output:
                # 解析找到的元素
                elements = []
                for part in output.split(", "):
                    if "FOUND:" in part and "POS:" in part:
                        try:
                            name_part = part.split("|POS:")[0].replace("FOUND:", "")
                            pos_part = part.split("|POS:")[1].split("|SIZE:")[0]
                            size_part = part.split("|SIZE:")[1] if "|SIZE:" in part else ""
                            
                            x, y = map(int, pos_part.split(","))
                            w, h = map(int, size_part.split(",")) if size_part else (0, 0)
                            
                            elements.append({
                                "name": name_part,
                                "position": {"x": x, "y": y},
                                "size": {"width": w, "height": h},
                                "center": {"x": x + w//2, "y": y + h//2}
                            })
                        except:
                            pass
                
                if elements:
                    return ToolResult(
                        success=True,
                        data={
                            "found": True,
                            "elements": elements,
                            "count": len(elements),
                            "suggestion": f"可以使用 gui_automation 工具点击位置 ({elements[0]['center']['x']}, {elements[0]['center']['y']})"
                        }
                    )
        
        # 如果 Accessibility API 找不到，尝试使用 OCR + 文字定位
        screenshot_path = await self._capture_screenshot("window" if app_name else "full", app_name)
        if screenshot_path:
            text = await self._ocr_image(screenshot_path)
            if target.lower() in text.lower():
                return ToolResult(
                    success=True,
                    data={
                        "found": True,
                        "method": "ocr",
                        "note": f"在屏幕文字中找到了 '{target}'，但无法确定精确位置",
                        "ocr_text": text[:500]
                    }
                )
        
        return ToolResult(
            success=True,
            data={
                "found": False,
                "message": f"未找到包含 '{target}' 的元素"
            }
        )
    
    async def _read_screen(self, kwargs: Dict[str, Any]) -> ToolResult:
        """读取屏幕上的文字"""
        area = kwargs.get("area", "full")
        app_name = kwargs.get("app_name", "")
        region = kwargs.get("region")
        
        screenshot_path = await self._capture_screenshot(area, app_name, region)
        if not screenshot_path:
            return ToolResult(success=False, error="截图失败")
        
        text = await self._ocr_image(screenshot_path)
        
        return ToolResult(
            success=True,
            data={
                "text": text,
                "char_count": len(text),
                "line_count": len(text.split("\n")),
                "screenshot_path": screenshot_path
            }
        )
    
    async def _describe_window(self, kwargs: Dict[str, Any]) -> ToolResult:
        """描述指定窗口的内容"""
        app_name = kwargs.get("app_name", "")
        
        if not app_name:
            return ToolResult(success=False, error="需要提供 app_name")
        
        # 获取窗口信息
        script = f'''
tell application "System Events"
    tell process "{app_name}"
        if (count of windows) > 0 then
            set w to window 1
            set winName to name of w
            set winPos to position of w
            set winSize to size of w
            
            -- 获取 UI 元素概述
            set buttonList to name of every button of w
            set textFields to name of every text field of w
            set staticTexts to name of every static text of w
            
            return "WINDOW:" & winName & "|POS:" & (item 1 of winPos) & "," & (item 2 of winPos) & "|SIZE:" & (item 1 of winSize) & "," & (item 2 of winSize) & "|BUTTONS:" & (buttonList as string) & "|TEXTS:" & (staticTexts as string)
        else
            return "NO_WINDOW"
        end if
    end tell
end tell
'''
        
        process = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        output = stdout.decode().strip()
        
        if output == "NO_WINDOW":
            return ToolResult(success=False, error=f"应用 {app_name} 没有打开的窗口")
        
        # 解析输出
        window_info = {}
        for part in output.split("|"):
            if ":" in part:
                key, value = part.split(":", 1)
                window_info[key.lower()] = value
        
        # 同时截图并 OCR
        screenshot_path = await self._capture_screenshot("window", app_name)
        text = ""
        if screenshot_path:
            text = await self._ocr_image(screenshot_path)
        
        return ToolResult(
            success=True,
            data={
                "app_name": app_name,
                "window_info": window_info,
                "screen_text": text[:1000] if text else "",
                "screenshot_path": screenshot_path
            }
        )
    
    async def _get_qrcode(self, kwargs: Dict[str, Any]) -> ToolResult:
        """截取并识别二维码"""
        app_name = kwargs.get("app_name", "")
        area = kwargs.get("area", "window" if app_name else "full")
        region = kwargs.get("region")
        
        screenshot_path = await self._capture_screenshot(area, app_name, region)
        if not screenshot_path:
            return ToolResult(success=False, error="截图失败")
        
        qrcode_content = await self._detect_qrcode(screenshot_path)
        
        # 读取图片作为 base64
        with open(screenshot_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode()
        
        if qrcode_content:
            return ToolResult(
                success=True,
                data={
                    "found": True,
                    "qrcode_content": qrcode_content,
                    "screenshot_path": screenshot_path,
                    "image_base64": image_base64
                }
            )
        else:
            return ToolResult(
                success=True,
                data={
                    "found": False,
                    "message": "未在截图中找到二维码",
                    "screenshot_path": screenshot_path,
                    "image_base64": image_base64,
                    "suggestion": "尝试调整截图区域，或确保二维码完整显示在屏幕上"
                }
            )
