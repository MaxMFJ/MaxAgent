"""
macOS 中文字体注册工具
为 reportlab 注册系统中文字体，解决 PDF 中文乱码问题。

使用方式（在 LLM 生成的脚本中）：
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # 如果不在 backend 目录
    from utils.pdf_fonts import register_chinese_fonts, CHINESE_FONT, CHINESE_FONT_BOLD
"""

import logging
import os

logger = logging.getLogger(__name__)

CHINESE_FONT = "ChineseFont"
CHINESE_FONT_BOLD = "ChineseFontBold"

_registered = False

# macOS 上可用的中文字体路径（按优先级排列）
_FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

_BOLD_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


def _find_font(candidates: list) -> str | None:
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def register_chinese_fonts() -> bool:
    """
    注册中文字体到 reportlab。成功返回 True。
    注册后可在 ParagraphStyle / canvas 中使用 CHINESE_FONT / CHINESE_FONT_BOLD。
    """
    global _registered
    if _registered:
        return True

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_path = _find_font(_FONT_CANDIDATES)
        if not font_path:
            logger.warning("No Chinese font found on this system")
            return False

        pdfmetrics.registerFont(TTFont(CHINESE_FONT, font_path))

        bold_path = _find_font(_BOLD_CANDIDATES)
        if bold_path:
            pdfmetrics.registerFont(TTFont(CHINESE_FONT_BOLD, bold_path))
        else:
            pdfmetrics.registerFont(TTFont(CHINESE_FONT_BOLD, font_path))

        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            CHINESE_FONT,
            normal=CHINESE_FONT,
            bold=CHINESE_FONT_BOLD,
            italic=CHINESE_FONT,
            boldItalic=CHINESE_FONT_BOLD,
        )

        _registered = True
        logger.info(f"Chinese fonts registered: {font_path}")
        return True

    except Exception as e:
        logger.warning(f"Failed to register Chinese fonts: {e}")
        return False
