"""
Screenshot Tool - 截图 + OCR 识别
系统调用通过 runtime adapter，禁止直接使用平台命令
"""

import os
import time
import asyncio
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
- 截取微信窗口：screenshot(action="capture", app_name="WeChat") — 激活该应用后全屏截图，坐标可直接用于 mouse_click
- 截取 Safari：screenshot(action="capture", app_name="Safari")
- 截取全屏：screenshot(action="capture", area="full")

【重要】
1. 传 app_name 会先激活该应用，然后截取全屏。截图坐标与 input_control.mouse_click 的屏幕坐标一致
2. 截图完成后立即结束任务，图片会自动显示，不需要做 OCR 或其他分析
3. GUI 操作前务必截图，根据截图中 UI 元素的位置确定 mouse_click 坐标"""
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
        """截图（通过 runtime adapter）"""
        if not self.runtime_adapter:
            return ToolResult(success=False, error="当前平台不支持截图")
        
        if not save_path:
            timestamp = int(time.time())
            save_path = f"/tmp/screenshot_{timestamp}.png"
        os.makedirs(os.path.dirname(save_path) or "/tmp", exist_ok=True)
        
        if delay > 0:
            await asyncio.sleep(delay)
        
        if app_name:
            return await self._capture_app_window(app_name, save_path)
        
        if area == "selection":
            ok, err = await self.runtime_adapter.screenshot_interactive(save_path)
        else:
            ok, err = await self.runtime_adapter.screenshot_full(save_path)
        
        if not ok:
            return ToolResult(success=False, error=err or "截图失败")
        if not os.path.exists(save_path):
            return ToolResult(success=False, error="截图被取消或失败")
        
        return await self._encode_and_return(save_path, area=area)
    
    async def _capture_app_window(self, app_name: str, save_path: str) -> ToolResult:
        """
        截取指定应用的截图。
        策略：先激活应用窗口，然后截取全屏。
        这样坐标系与 input_control.mouse_click 的屏幕坐标一致，
        LLM 从截图中读取的坐标可以直接用于 mouse_click。
        """
        # 激活目标应用
        await self.runtime_adapter.activate_app(app_name)
        await asyncio.sleep(0.5)
        
        # 获取窗口位置信息（供 LLM 参考）
        window_info = {}
        try:
            ok, info, err = await self.runtime_adapter.get_window_info(app_name)
            if ok and info:
                window_info = info
        except Exception:
            pass
        
        # 截取全屏（坐标与 mouse_click 一致）
        ok, err = await self.runtime_adapter.screenshot_full(save_path)
        if ok and os.path.exists(save_path):
            result = await self._encode_and_return(save_path, area="full", app_name=app_name)
            if result.success and window_info:
                result.data["window_info"] = window_info
                result.data["note"] = f"已激活 {app_name} 窗口。这是全屏截图，坐标可直接用于 mouse_click。"
            return result
        
        return ToolResult(success=False, error=err or "截图失败")
    
    async def _encode_and_return(
        self, save_path: str, area: str = "full", app_name: Optional[str] = None
    ) -> ToolResult:
        """读取图片、转 base64 并返回结果"""
        if not os.path.exists(save_path):
            return ToolResult(success=False, error="截图文件不存在")
        file_size = os.path.getsize(save_path)
        image_base64 = None
        try:
            with open(save_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to encode screenshot: {e}")
        result_data = {
            "screenshot_path": save_path, "path": save_path, "size": file_size,
            "area": area, "message": f"截图已保存到 {save_path}"
        }
        if app_name:
            result_data["app_name"] = app_name
        if image_base64:
            result_data["image_base64"] = image_base64
            result_data["mime_type"] = "image/png"
        return ToolResult(success=True, data=result_data)
    
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
