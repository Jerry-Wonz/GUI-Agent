"""OCR 辅助定位模块。

在 ShowUI 预测坐标附近进行 OCR 文本识别，对 text 类型元素做二次确认。
"""

from __future__ import annotations

import re
from pathlib import Path

import easyocr
from PIL import Image


# 预编译文本清理正则
_CLEAN_RE = re.compile(r"[^a-zA-Z0-9一-鿿\s]")


def _clean_text(text: str) -> str:
    """清理 OCR 识别文本：去除非字母数字/中文的字符。"""
    return _CLEAN_RE.sub("", text).strip().lower()


class OCRHelper:
    """轻量 OCR 辅助工具，用于 text 元素定位确认。

    在 ShowUI 预测坐标附近区域运行 OCR，验证目标文本是否存在。
    """

    def __init__(self, gpu: bool = True) -> None:
        self.reader = easyocr.Reader(["en"], gpu=gpu)

    def extract_text_at_point(
        self, image_path: str, point: list[float],
        crop_ratio: float = 0.1,
    ) -> list[dict]:
        """在预测坐标附近提取文本。

        Args:
            image_path: 图片路径
            point: 归一化坐标 [x, y]
            crop_ratio: 裁剪区域占图片比例（如 0.1 = 以点为中心取 10% 区域）
        Returns:
            text_regions: [{"text": str, "confidence": float, "bbox": [x1,y1,x2,y2]}, ...]
        """
        img = Image.open(image_path).convert("RGB")
        img_w, img_h = img.size

        # 计算裁剪区域（像素坐标）
        cx = int(point[0] * img_w)
        cy = int(point[1] * img_h)
        crop_w = int(img_w * crop_ratio)
        crop_h = int(img_h * crop_ratio)

        left = max(0, cx - crop_w // 2)
        top = max(0, cy - crop_h // 2)
        right = min(img_w, cx + crop_w // 2)
        bottom = min(img_h, cy + crop_h // 2)

        # 裁剪并 OCR
        cropped = img.crop((left, top, right, bottom))
        import numpy as np
        cropped_np = np.array(cropped)
        results = self.reader.readtext(cropped_np)

        # 转换为归一化坐标
        text_regions = []
        for bbox, text, confidence in results:
            x1 = (left + bbox[0][0]) / img_w
            y1 = (top + bbox[0][1]) / img_h
            x2 = (left + bbox[2][0]) / img_w
            y2 = (top + bbox[2][1]) / img_h
            text_regions.append({
                "text": text,
                "confidence": confidence,
                "bbox": [x1, y1, x2, y2],
            })

        return text_regions

    def match_text_at_point(
        self, image_path: str, query: str, point: list[float],
        crop_ratio: float = 0.15,
    ) -> dict | None:
        """检查预测点附近是否有与指令匹配的文本（严格匹配）。

        Args:
            image_path: 图片路径
            query: 指令文本，如 "search button"
            point: ShowUI 预测的归一化坐标
            crop_ratio: 搜索区域大小
        Returns:
            匹配结果: {"text": str, "confidence": float, "bbox": [x1,y1,x2,y2]}
            不匹配或无文本返回 None
        """
        query_clean = _clean_text(query)
        if not query_clean:
            return None

        query_words = query_clean.split()
        if not query_words:
            return None

        regions = self.extract_text_at_point(image_path, point, crop_ratio)
        for region in regions:
            region_clean = _clean_text(region["text"])
            if region["confidence"] < 0.5:
                continue
            # 严格匹配：至少 50% 的指令词出现在 OCR 文本中
            matches = sum(1 for w in query_words if w in region_clean)
            if matches / len(query_words) >= 0.5:
                return region

        return None

        return None

    def search_text_on_page(
        self, image_path: str, query: str,
    ) -> list[dict]:
        """在全页搜索与指令匹配的文本区域。

        Returns:
            匹配的文本区域列表，按置信度排序
        """
        query_clean = _clean_text(query)
        if not query_clean:
            return []

        query_words = query_clean.split()
        results = self.reader.readtext(image_path)

        matches = []
        for bbox, text, confidence in results:
            text_clean = _clean_text(text)
            match_score = sum(
                1 for w in query_words
                if w in text_clean or text_clean in w
            )
            if match_score > 0 and confidence > 0.3:
                x1 = bbox[0][0]
                y1 = bbox[0][1]
                x2 = bbox[2][0]
                y2 = bbox[2][1]
                matches.append({
                    "text": text,
                    "confidence": confidence,
                    "bbox": [x1, y1, x2, y2],
                    "match_score": match_score,
                })

        matches.sort(key=lambda m: (m["match_score"], m["confidence"]), reverse=True)
        return matches