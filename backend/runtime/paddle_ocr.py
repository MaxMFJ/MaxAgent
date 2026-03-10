"""
PaddleOCR Runtime — 图像预处理 + OCR 识别 + Layout 结构化 + 语义匹配
提供比 Swift Vision / Tesseract 更高精度的中文 OCR 能力

底层引擎优先级：
  1. RapidOCR (ONNX Runtime) — 兼容性更好，支持 Python 3.14+
  2. PaddleOCR (PaddlePaddle) — 需要 Python ≤3.12
两者 API 不同但 OCR 模型相同（PaddleOCR 的 ONNX 导出版本）
"""

import os
import logging
import asyncio
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# 懒加载标志
_paddleocr_engine = None
_cv2 = None
_np = None


def _lazy_import_cv2():
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2


def _lazy_import_np():
    global _np
    if _np is None:
        import numpy as np
        _np = np
    return _np


def _get_ocr_engine():
    """懒加载 OCR 引擎（优先 RapidOCR，回退 PaddleOCR）"""
    global _paddleocr_engine
    if _paddleocr_engine is not None:
        return _paddleocr_engine

    # 优先尝试 RapidOCR (ONNX Runtime) — 兼容 Python 3.14+
    try:
        from rapidocr_onnxruntime import RapidOCR
        _paddleocr_engine = ("rapid", RapidOCR())
        logger.info("[OCR] RapidOCR (ONNX) engine initialized")
        return _paddleocr_engine
    except ImportError:
        pass

    # 回退到 PaddleOCR（需要 Python ≤3.12）
    try:
        from paddleocr import PaddleOCR
        _paddleocr_engine = ("paddle", PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,
            use_gpu=False,
            det_db_thresh=0.3,
            det_db_box_thresh=0.5,
            rec_batch_num=8,
        ))
        logger.info("[OCR] PaddleOCR engine initialized")
        return _paddleocr_engine
    except ImportError:
        logger.warning("[OCR] Neither rapidocr-onnxruntime nor paddleocr installed, OCR unavailable")
        return None


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class OCRLayoutItem:
    """单个 OCR 识别结果，含位置信息"""
    text: str
    confidence: float
    bbox: List[float]        # [x1, y1, x2, y2]
    center_x: float = 0.0
    center_y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    line_group_id: int = -1

    def __post_init__(self):
        if self.bbox and len(self.bbox) == 4:
            x1, y1, x2, y2 = self.bbox
            self.center_x = (x1 + x2) / 2
            self.center_y = (y1 + y2) / 2
            self.width = x2 - x1
            self.height = y2 - y1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OCRLayout:
    """完整 OCR 识别结果"""
    items: List[OCRLayoutItem] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    full_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "image_width": self.image_width,
            "image_height": self.image_height,
            "full_text": self.full_text,
            "item_count": len(self.items),
        }


@dataclass
class SemanticMatch:
    """语义匹配结果"""
    item: OCRLayoutItem
    score: float
    method: str  # "exact", "contains", "fuzzy"


# ---------------------------------------------------------------------------
# 图像预处理管道 (阶段 3)
# ---------------------------------------------------------------------------

def preprocess_image(image_path: str, output_path: Optional[str] = None) -> str:
    """
    图像预处理管道：灰度 → 对比度增强(CLAHE) → 去噪 → 自适应阈值 → 锐化 → DPI 归一化
    返回预处理后的图像路径
    """
    cv2 = _lazy_import_cv2()
    np = _lazy_import_np()

    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"[Preprocess] Cannot read image: {image_path}")
        return image_path

    # 1. 转灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE 对比度增强
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 3. 高斯去噪
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    # 4. 锐化
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(denoised, -1, kernel)

    # 5. DPI 归一化 — 确保短边 >= 960px（≈ 300dpi 效果）
    h, w = sharpened.shape[:2]
    min_dim = min(h, w)
    if min_dim < 960:
        scale = 960 / min_dim
        new_w, new_h = int(w * scale), int(h * scale)
        sharpened = cv2.resize(sharpened, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    if output_path is None:
        base, ext = os.path.splitext(image_path)
        output_path = f"{base}_preprocessed{ext}"

    cv2.imwrite(output_path, sharpened)
    return output_path


# ---------------------------------------------------------------------------
# PaddleOCR Pipeline (阶段 4 + 5)
# ---------------------------------------------------------------------------

async def run_paddle_ocr(
    image_path: str,
    preprocess: bool = True,
) -> Optional[OCRLayout]:
    """
    执行 OCR 识别（RapidOCR 或 PaddleOCR），返回结构化 OCRLayout。
    preprocess=True 时先执行图像预处理管道。
    """
    engine_tuple = _get_ocr_engine()
    if engine_tuple is None:
        return None

    engine_type, engine = engine_tuple
    cv2 = _lazy_import_cv2()

    # 图像预处理
    ocr_path = image_path
    if preprocess:
        preprocessed = f"/tmp/paddle_ocr_prep_{os.path.basename(image_path)}"
        ocr_path = await asyncio.to_thread(preprocess_image, image_path, preprocessed)

    # OCR 推理（CPU 密集，放到线程池）
    if engine_type == "rapid":
        result_raw, _ = await asyncio.to_thread(engine, ocr_path)
        # RapidOCR 返回: [[bbox_points, text, confidence], ...] 或 None
        raw_lines = result_raw if result_raw else []
    else:
        result_raw = await asyncio.to_thread(engine.ocr, ocr_path, cls=True)
        # PaddleOCR 返回: [[[bbox_points, (text, confidence)], ...]]
        raw_lines = result_raw[0] if (result_raw and result_raw[0]) else []

    if not raw_lines:
        return OCRLayout()

    # 读取原始图像尺寸
    orig_img = cv2.imread(image_path)
    img_h, img_w = (orig_img.shape[:2]) if orig_img is not None else (0, 0)

    # 构建 OCRLayoutItem 列表
    items: List[OCRLayoutItem] = []
    for line in raw_lines:
        if engine_type == "rapid":
            # RapidOCR: [bbox_points, text, confidence]
            bbox_points = line[0]
            text = line[1]
            confidence = float(line[2])
        else:
            # PaddleOCR: [bbox_points, (text, confidence)]
            bbox_points = line[0]
            text, confidence = line[1]

        # 将四点坐标转为 [x1, y1, x2, y2]
        xs = [p[0] for p in bbox_points]
        ys = [p[1] for p in bbox_points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]

        # 如果做了预处理缩放，需要映射回原始坐标
        if preprocess and ocr_path != image_path:
            prep_img = cv2.imread(ocr_path)
            if prep_img is not None and img_w > 0:
                ph, pw = prep_img.shape[:2]
                scale_x = img_w / pw
                scale_y = img_h / ph
                bbox = [bbox[0] * scale_x, bbox[1] * scale_y,
                        bbox[2] * scale_x, bbox[3] * scale_y]

        items.append(OCRLayoutItem(
            text=text,
            confidence=confidence,
            bbox=bbox,
        ))

    # 行分组：根据 y 坐标中心点聚类
    _assign_line_groups(items)

    # 构建全文
    full_text = "\n".join(item.text for item in items)

    layout = OCRLayout(
        items=items,
        image_width=img_w,
        image_height=img_h,
        full_text=full_text,
    )

    # 清理临时预处理文件
    if preprocess and ocr_path != image_path and os.path.exists(ocr_path):
        try:
            os.remove(ocr_path)
        except OSError:
            pass

    return layout


def _assign_line_groups(items: List[OCRLayoutItem], threshold: float = 15.0):
    """将 OCR 结果按 y 坐标中心点聚成行组"""
    if not items:
        return
    sorted_items = sorted(items, key=lambda it: it.center_y)
    group_id = 0
    current_y = sorted_items[0].center_y
    for item in sorted_items:
        if abs(item.center_y - current_y) > threshold:
            group_id += 1
            current_y = item.center_y
        item.line_group_id = group_id


# ---------------------------------------------------------------------------
# GUI Semantic Resolver (阶段 6)
# ---------------------------------------------------------------------------

def resolve_target(
    layout: OCRLayout,
    target_text: str,
    image_width: int = 0,
    image_height: int = 0,
) -> Optional[SemanticMatch]:
    """
    在 OCRLayout 中查找与 target_text 最匹配的元素。
    评分公式:
        score = semantic_similarity * 0.6
              + confidence * 0.2
              + center_bias * 0.1
              + click_prior * 0.1
    """
    if not layout.items or not target_text:
        return None

    iw = image_width or layout.image_width or 1
    ih = image_height or layout.image_height or 1

    best: Optional[SemanticMatch] = None
    target_lower = target_text.lower().strip()

    for item in layout.items:
        text_lower = item.text.lower().strip()

        # 语义相似度
        if text_lower == target_lower:
            sim = 1.0
            method = "exact"
        elif target_lower in text_lower or text_lower in target_lower:
            sim = 0.85
            method = "contains"
        else:
            sim = SequenceMatcher(None, target_lower, text_lower).ratio()
            method = "fuzzy"

        # 置信度分
        conf_score = item.confidence

        # 中心偏好：靠近屏幕中心的元素略加分
        cx_ratio = abs(item.center_x / iw - 0.5) if iw else 0
        cy_ratio = abs(item.center_y / ih - 0.5) if ih else 0
        center_bias = 1.0 - (cx_ratio + cy_ratio) / 2

        # 可点击先验：较小的元素更可能是按钮/链接
        area_ratio = (item.width * item.height) / (iw * ih) if (iw * ih) else 0
        click_prior = 1.0 - min(area_ratio * 10, 1.0)

        score = sim * 0.6 + conf_score * 0.2 + center_bias * 0.1 + click_prior * 0.1

        if best is None or score > best.score:
            best = SemanticMatch(item=item, score=score, method=method)

    # 过滤低分匹配
    if best and best.score < 0.3:
        return None

    return best


def find_all_matches(
    layout: OCRLayout,
    target_text: str,
    min_score: float = 0.4,
) -> List[SemanticMatch]:
    """返回所有分数 >= min_score 的匹配项，按分数降序"""
    if not layout.items or not target_text:
        return []

    iw = layout.image_width or 1
    ih = layout.image_height or 1
    target_lower = target_text.lower().strip()
    matches: List[SemanticMatch] = []

    for item in layout.items:
        text_lower = item.text.lower().strip()

        if text_lower == target_lower:
            sim, method = 1.0, "exact"
        elif target_lower in text_lower or text_lower in target_lower:
            sim, method = 0.85, "contains"
        else:
            sim = SequenceMatcher(None, target_lower, text_lower).ratio()
            method = "fuzzy"

        conf_score = item.confidence
        cx_ratio = abs(item.center_x / iw - 0.5)
        cy_ratio = abs(item.center_y / ih - 0.5)
        center_bias = 1.0 - (cx_ratio + cy_ratio) / 2
        area_ratio = (item.width * item.height) / (iw * ih) if (iw * ih) else 0
        click_prior = 1.0 - min(area_ratio * 10, 1.0)

        score = sim * 0.6 + conf_score * 0.2 + center_bias * 0.1 + click_prior * 0.1
        if score >= min_score:
            matches.append(SemanticMatch(item=item, score=score, method=method))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


# ---------------------------------------------------------------------------
# 便捷 API
# ---------------------------------------------------------------------------

async def ocr_full_text(image_path: str, preprocess: bool = True) -> str:
    """仅返回全文文本（用于替代 Swift Vision / Tesseract）"""
    layout = await run_paddle_ocr(image_path, preprocess=preprocess)
    if layout is None:
        return ""
    return layout.full_text


async def find_text_coords(
    image_path: str,
    target_text: str,
    preprocess: bool = True,
) -> Optional[Dict[str, Any]]:
    """查找文字并返回坐标信息，如未找到返回 None"""
    layout = await run_paddle_ocr(image_path, preprocess=preprocess)
    if layout is None:
        return None

    match = resolve_target(layout, target_text)
    if match is None:
        return None

    return {
        "found": True,
        "text": match.item.text,
        "confidence": match.item.confidence,
        "score": match.score,
        "method": match.method,
        "center_x": match.item.center_x,
        "center_y": match.item.center_y,
        "bbox": match.item.bbox,
    }


def is_available() -> bool:
    """检查 OCR 引擎（RapidOCR 或 PaddleOCR）是否可用"""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import paddleocr  # noqa: F401
        return True
    except ImportError:
        logger.info("[OCR] Neither rapidocr-onnxruntime nor paddleocr installed.")
        return False
