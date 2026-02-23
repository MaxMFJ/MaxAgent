"""
Screenshot Tool - 截图 + OCR 识别
"""

import os
import time
import asyncio
import subprocess
import base64
import logging
from typing import Optional
from .base import BaseTool, ToolResult, ToolCategory

logger = logging.getLogger(__name__)


class ScreenshotTool(BaseTool):
    """截图工具，支持全屏、窗口、区域截图，以及 OCR 文字识别"""
    
    name = "screenshot"
    description = """截取屏幕截图。截图会自动显示在聊天窗口中，截图完成后无需做任何额外操作。

使用方法：
- 截取微信窗口：screenshot(action="capture", app_name="WeChat")
- 截取 Safari：screenshot(action="capture", app_name="Safari")
- 截取全屏：screenshot(action="capture", area="full")

【重要】
1. 必须使用 app_name 参数指定应用名称，才能自动截取窗口
2. 截图完成后立即结束任务，图片会自动显示，不需要做 OCR 或其他分析"""
    category = ToolCategory.SYSTEM
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["capture", "ocr", "capture_and_ocr"],
                "description": "操作类型：capture=截图, ocr=识别图片文字, capture_and_ocr=截图并识别"
            },
            "area": {
                "type": "string",
                "enum": ["full", "window", "selection"],
                "description": "截图区域：full=全屏, window=窗口, selection=手动选择"
            },
            "app_name": {
                "type": "string",
                "description": "应用程序名称（如 '微信'、'Safari'），指定后会自动截取该应用窗口，无需用户交互"
            },
            "save_path": {
                "type": "string",
                "description": "截图保存路径（可选，默认保存到临时目录）"
            },
            "image_path": {
                "type": "string",
                "description": "要进行 OCR 识别的图片路径（action=ocr 时必需）"
            },
            "delay": {
                "type": "number",
                "description": "截图延迟秒数（可选）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(
        self,
        action: str = "capture",
        area: str = "full",
        app_name: Optional[str] = None,
        save_path: Optional[str] = None,
        image_path: Optional[str] = None,
        delay: float = 0
    ) -> ToolResult:
        """执行截图或 OCR 操作"""
        
        if action == "capture":
            return await self._capture(area, save_path, delay, app_name)
        elif action == "ocr":
            if not image_path:
                return ToolResult(success=False, error="OCR 需要提供 image_path 参数")
            return await self._ocr(image_path)
        elif action == "capture_and_ocr":
            capture_result = await self._capture(area, save_path, delay, app_name)
            if not capture_result.success:
                return capture_result
            
            captured_path = capture_result.data.get("path")
            ocr_result = await self._ocr(captured_path)
            
            # 同时返回图片 base64
            result_data = {
                "screenshot_path": captured_path,
                "ocr_text": ocr_result.data.get("text") if ocr_result.success else None,
                "ocr_error": ocr_result.error if not ocr_result.success else None
            }
            
            # 添加 base64 图片数据
            if capture_result.data.get("image_base64"):
                result_data["image_base64"] = capture_result.data["image_base64"]
                result_data["mime_type"] = capture_result.data.get("mime_type", "image/png")
            
            return ToolResult(success=True, data=result_data)
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _capture(
        self,
        area: str,
        save_path: Optional[str],
        delay: float,
        app_name: Optional[str] = None
    ) -> ToolResult:
        """截图"""
        # 生成保存路径
        if not save_path:
            timestamp = int(time.time())
            save_path = f"/tmp/screenshot_{timestamp}.png"
        
        # 确保目录存在
        os.makedirs(os.path.dirname(save_path) or "/tmp", exist_ok=True)
        
        # 如果指定了应用名称，使用自动窗口截图
        if app_name:
            return await self._capture_app_window(app_name, save_path, delay)
        
        # 构建截图命令
        cmd = ["screencapture", "-x"]  # -x 静默模式，不发出声音
        
        if delay > 0:
            cmd.extend(["-T", str(int(delay))])
        
        # 注意：不再使用 -w (交互式窗口选择)，因为需要用户操作
        # 如果需要窗口截图，应该使用 app_name 参数
        if area == "selection":
            cmd.append("-i")  # 交互式选择（保留，因为有时确实需要用户选择区域）
        # full 和 window (无 app_name) 都使用全屏截图
        
        cmd.append(save_path)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                return ToolResult(success=False, error=f"截图失败: {stderr.decode()}")
            
            if not os.path.exists(save_path):
                return ToolResult(success=False, error="截图被取消或失败")
            
            file_size = os.path.getsize(save_path)
            
            # 读取图片并转换为 base64，以便在聊天窗口中显示
            image_base64 = None
            try:
                with open(save_path, "rb") as f:
                    image_data = f.read()
                    image_base64 = base64.b64encode(image_data).decode("utf-8")
                    logger.info(f"Successfully encoded screenshot to base64, length={len(image_base64)}")
            except Exception as e:
                logger.error(f"Failed to encode screenshot to base64: {e}")
            
            result_data = {
                "screenshot_path": save_path,
                "path": save_path,
                "size": file_size,
                "area": area,
                "message": f"截图已保存到 {save_path}"
            }
            
            # 如果成功读取了 base64 数据，添加到结果中
            if image_base64:
                result_data["image_base64"] = image_base64
                result_data["mime_type"] = "image/png"
            
            return ToolResult(
                success=True,
                data=result_data
            )
        except Exception as e:
            return ToolResult(success=False, error=f"截图异常: {str(e)}")
    
    async def _capture_app_window(
        self,
        app_name: str,
        save_path: str,
        delay: float
    ) -> ToolResult:
        """自动截取指定应用的窗口（无需用户交互）"""
        
        if delay > 0:
            await asyncio.sleep(delay)
        
        # 首先激活应用窗口
        activate_script = f'''
tell application "{app_name}"
    activate
end tell
delay 0.3
'''
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", activate_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except:
            pass
        
        # 获取窗口 ID
        window_id = await self._get_window_id(app_name)
        
        if window_id:
            # 使用窗口 ID 直接截图（无需用户交互）
            cmd = ["screencapture", "-x", "-l", str(window_id), save_path]
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await process.communicate()
                
                if process.returncode == 0 and os.path.exists(save_path):
                    file_size = os.path.getsize(save_path)
                    
                    # 读取图片并转换为 base64
                    image_base64 = None
                    try:
                        with open(save_path, "rb") as f:
                            image_data = f.read()
                            image_base64 = base64.b64encode(image_data).decode("utf-8")
                    except:
                        pass
                    
                    result_data = {
                        "screenshot_path": save_path,
                        "path": save_path,
                        "size": file_size,
                        "area": "window",
                        "app_name": app_name,
                        "window_id": window_id,
                        "message": f"已截取 {app_name} 窗口"
                    }
                    
                    if image_base64:
                        result_data["image_base64"] = image_base64
                        result_data["mime_type"] = "image/png"
                    
                    return ToolResult(success=True, data=result_data)
            except Exception as e:
                return ToolResult(success=False, error=f"截图失败: {str(e)}")
        
        # 备用方案：使用窗口边界截图
        bounds = await self._get_window_bounds(app_name)
        if bounds:
            x, y, w, h = bounds
            # 使用区域截图
            region_str = f"{int(x)},{int(y)},{int(w)},{int(h)}"
            cmd = ["screencapture", "-x", "-R", region_str, save_path]
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                if os.path.exists(save_path):
                    file_size = os.path.getsize(save_path)
                    
                    image_base64 = None
                    try:
                        with open(save_path, "rb") as f:
                            image_data = f.read()
                            image_base64 = base64.b64encode(image_data).decode("utf-8")
                    except:
                        pass
                    
                    result_data = {
                        "screenshot_path": save_path,
                        "path": save_path,
                        "size": file_size,
                        "area": "window",
                        "app_name": app_name,
                        "bounds": bounds,
                        "message": f"已截取 {app_name} 窗口区域"
                    }
                    
                    if image_base64:
                        result_data["image_base64"] = image_base64
                        result_data["mime_type"] = "image/png"
                    
                    return ToolResult(success=True, data=result_data)
            except:
                pass
        
        logger.error(f"无法获取 {app_name} 的窗口信息，尝试全屏截图作为后备")
        # 最后的后备方案：使用全屏截图
        return await self._capture(area="full", save_path=save_path, delay=0)
    
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
            match_names = list(set(match_names))  # 去重
            
            for window in windows:
                owner = window.get(Quartz.kCGWindowOwnerName, "")
                owner_lower = owner.lower()
                
                # 检查是否匹配任何可能的名称
                matched = False
                for match_name in match_names:
                    if match_name in owner_lower or owner_lower in match_name:
                        matched = True
                        break
                
                if matched:
                    layer = window.get(Quartz.kCGWindowLayer, 0)
                    if layer == 0:  # 普通窗口层
                        window_id = window.get(Quartz.kCGWindowNumber, 0)
                        if window_id > 0:
                            logger.info(f"Got window ID for {app_name} (owner={owner}): {window_id}")
                            return window_id
            
            logger.warning(f"No window ID found for {app_name}")
            return None
            
        except ImportError:
            logger.warning("Quartz module not available, trying subprocess fallback")
            return await self._get_window_id_subprocess(app_name)
        except Exception as e:
            logger.error(f"_get_window_id error: {e}")
            return None
    
    async def _get_window_id_subprocess(self, app_name: str) -> Optional[int]:
        """使用子进程获取窗口 ID（备用方案）"""
        py_script = f'''
import Quartz
import sys

windows = Quartz.CGWindowListCopyWindowInfo(
    Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
    Quartz.kCGNullWindowID
)

app_name_lower = "{app_name}".lower()
for window in windows:
    owner = window.get(Quartz.kCGWindowOwnerName, "")
    owner_lower = owner.lower()
    if app_name_lower in owner_lower or owner_lower in app_name_lower:
        layer = window.get(Quartz.kCGWindowLayer, 0)
        if layer == 0:
            print(window.get(Quartz.kCGWindowNumber, 0))
            sys.exit(0)

print(0)
'''
        try:
            import sys
            python_path = sys.executable  # 使用当前 Python 解释器
            process = await asyncio.create_subprocess_exec(
                python_path, "-c", py_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if stderr:
                logger.warning(f"_get_window_id_subprocess stderr: {stderr.decode()}")
            
            output = stdout.decode().strip()
            if output:
                window_id = int(output)
                if window_id > 0:
                    logger.info(f"Got window ID via subprocess for {app_name}: {window_id}")
                    return window_id
        except Exception as e:
            logger.error(f"_get_window_id_subprocess error: {e}")
        
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
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode().strip()
                parts = output.split(",")
                if len(parts) == 4:
                    bounds = tuple(int(p.strip()) for p in parts)
                    logger.info(f"Got window bounds for {app_name}: {bounds}")
                    return bounds
            else:
                logger.warning(f"_get_window_bounds failed: {stderr.decode()}")
        except Exception as e:
            logger.error(f"_get_window_bounds error: {e}")
        
        return None
    
    async def _ocr(self, image_path: str) -> ToolResult:
        """使用 macOS Vision 框架进行 OCR"""
        
        if not os.path.exists(image_path):
            return ToolResult(success=False, error=f"图片不存在: {image_path}")
        
        # 使用 Swift 脚本调用 Vision 框架
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
        
        # 保存 Swift 脚本
        script_path = "/tmp/ocr_script.swift"
        with open(script_path, "w") as f:
            f.write(swift_script)
        
        try:
            # 使用 swift 执行脚本
            process = await asyncio.create_subprocess_exec(
                "swift", script_path, image_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # 如果 Swift 脚本失败，尝试使用 shortcuts 或其他方法
                return await self._ocr_fallback(image_path)
            
            text = stdout.decode().strip()
            
            return ToolResult(
                success=True,
                data={
                    "text": text,
                    "image_path": image_path,
                    "char_count": len(text)
                }
            )
        except Exception as e:
            return await self._ocr_fallback(image_path)
    
    async def _ocr_fallback(self, image_path: str) -> ToolResult:
        """备用 OCR 方法：使用 shortcuts 或 tesseract"""
        
        # 尝试使用 tesseract（如果安装了的话）
        try:
            process = await asyncio.create_subprocess_exec(
                "tesseract", image_path, "stdout", "-l", "chi_sim+eng",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                text = stdout.decode().strip()
                return ToolResult(
                    success=True,
                    data={
                        "text": text,
                        "image_path": image_path,
                        "method": "tesseract"
                    }
                )
        except FileNotFoundError:
            pass
        
        return ToolResult(
            success=False,
            error="OCR 失败：需要安装 tesseract (brew install tesseract tesseract-lang)"
        )
