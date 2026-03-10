"""
VisionFallbackService — AX API 失败后的视觉回退层
Pipeline: 截图 → 预处理 → PaddleOCR → Layout 结构化 → 语义匹配 → 坐标返回
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import asdict

logger = logging.getLogger(__name__)


class VisionFallbackService:
    """
    当 AX API 无法找到目标元素时，使用 PaddleOCR 视觉管道作为回退。
    
    典型调用流程:
        1. AX query_elements() → 找不到
        2. VisionFallbackService.find_element_visual(target) → 截图+OCR+匹配
        3. 返回坐标 → Action Executor 执行点击
    """

    def __init__(self, runtime_adapter=None):
        self.runtime_adapter = runtime_adapter

    async def capture_screenshot(
        self,
        app_name: str = "",
        save_path: Optional[str] = None,
    ) -> Optional[str]:
        """截取屏幕截图，返回文件路径"""
        if not self.runtime_adapter:
            logger.error("[VisionFallback] No runtime adapter")
            return None

        if save_path is None:
            import time
            save_path = f"/tmp/vision_fallback_{int(time.time())}.png"

        if app_name:
            await self.runtime_adapter.activate_app(app_name)
            await asyncio.sleep(0.3)
            ok, _ = await self.runtime_adapter.screenshot_window(app_name, save_path)
            if ok and os.path.exists(save_path):
                return save_path
            logger.warning(f"[VisionFallback] Window capture failed for {app_name}, using full screen")

        ok, _ = await self.runtime_adapter.screenshot_full(save_path)
        if ok and os.path.exists(save_path):
            return save_path
        return None

    async def find_element_visual(
        self,
        target_text: str,
        app_name: str = "",
        screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        视觉查找 UI 元素。
        返回: {found, text, center_x, center_y, bbox, confidence, score, method, all_matches}
        """
        from runtime.paddle_ocr import run_paddle_ocr, resolve_target, find_all_matches, is_available

        if not is_available():
            return {"found": False, "error": "PaddleOCR not installed", "method": "vision_fallback"}

        # 截图
        if screenshot_path is None:
            screenshot_path = await self.capture_screenshot(app_name)
        if screenshot_path is None:
            return {"found": False, "error": "Screenshot failed", "method": "vision_fallback"}

        # PaddleOCR
        layout = await run_paddle_ocr(screenshot_path, preprocess=True)
        if layout is None:
            return {"found": False, "error": "PaddleOCR failed", "method": "vision_fallback"}

        # 语义匹配
        best = resolve_target(layout, target_text)
        all_matches = find_all_matches(layout, target_text, min_score=0.4)

        if best is None:
            return {
                "found": False,
                "method": "vision_fallback",
                "ocr_text": layout.full_text[:500],
                "item_count": len(layout.items),
            }

        return {
            "found": True,
            "method": "vision_fallback",
            "text": best.item.text,
            "center_x": best.item.center_x,
            "center_y": best.item.center_y,
            "bbox": best.item.bbox,
            "confidence": best.item.confidence,
            "score": best.score,
            "match_method": best.method,
            "all_matches": [
                {
                    "text": m.item.text,
                    "center_x": m.item.center_x,
                    "center_y": m.item.center_y,
                    "score": m.score,
                }
                for m in all_matches[:5]
            ],
        }

    async def read_screen_structured(
        self,
        app_name: str = "",
        screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        读取屏幕并返回结构化 OCR 结果（含位置信息）。
        比纯文本 OCR 多返回每个文字块的 bbox 和置信度。
        """
        from runtime.paddle_ocr import run_paddle_ocr, is_available

        if not is_available():
            return {"success": False, "error": "PaddleOCR not installed"}

        if screenshot_path is None:
            screenshot_path = await self.capture_screenshot(app_name)
        if screenshot_path is None:
            return {"success": False, "error": "Screenshot failed"}

        layout = await run_paddle_ocr(screenshot_path, preprocess=True)
        if layout is None:
            return {"success": False, "error": "PaddleOCR failed"}

        return {
            "success": True,
            "full_text": layout.full_text,
            "item_count": len(layout.items),
            "items": [item.to_dict() for item in layout.items],
            "image_width": layout.image_width,
            "image_height": layout.image_height,
        }

    async def verify_action(
        self,
        expected_change: str,
        app_name: str = "",
        screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        结果验证（阶段 8）：执行动作后重新截图 + OCR，检查 UI 是否发生预期变化。
        """
        from runtime.paddle_ocr import run_paddle_ocr, is_available

        if not is_available():
            return {"verified": False, "error": "PaddleOCR not installed"}

        if screenshot_path is None:
            screenshot_path = await self.capture_screenshot(app_name)
        if screenshot_path is None:
            return {"verified": False, "error": "Screenshot failed"}

        layout = await run_paddle_ocr(screenshot_path, preprocess=False)
        if layout is None:
            return {"verified": False, "error": "PaddleOCR failed"}

        # 在全文中搜索预期变化
        full_lower = layout.full_text.lower()
        expected_lower = expected_change.lower()
        found = expected_lower in full_lower

        return {
            "verified": found,
            "expected": expected_change,
            "ocr_text": layout.full_text[:500],
            "item_count": len(layout.items),
        }
