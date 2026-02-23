"""
Image Extractor - 从工具结果中抽取图片数据
从 Core 抽离，Core 不再直接读文件
供 main 或 stream 消费者调用
"""

import base64
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_image_from_result(data: Any) -> Optional[Dict[str, Any]]:
    """
    从工具返回的 data 中抽取图片，生成可下发的 image chunk
    Returns:
        {"type": "image", "base64": ..., "mime_type": ..., "path": ...} 或 None
    """
    if not isinstance(data, dict):
        return None

    if "image_base64" in data:
        base64_data = data["image_base64"]
        return {
            "type": "image",
            "base64": base64_data,
            "mime_type": data.get("mime_type", "image/png"),
            "path": data.get("screenshot_path") or data.get("path"),
        }

    if "screenshot_path" in data or "path" in data:
        path = data.get("screenshot_path") or data.get("path", "")
        if path and any(
            path.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]
        ):
            try:
                with open(path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")
                return {
                    "type": "image",
                    "base64": image_data,
                    "mime_type": "image/png",
                    "path": path,
                }
            except Exception as e:
                logger.warning(f"Failed to read image file: {e}")
                return {"type": "image", "path": path}

    return None
