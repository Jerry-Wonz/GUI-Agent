"""ShowUIEnhancedGrounder — ShowUI-2B 定位能力增强版。

在 ShowUIGrounder 基础上增加以下优化：
1. 坐标后处理优化（修复 EDGE_BIAS, OUT_OF_BOUNDS）
2. 多尺度滑动窗口推理（提高稳定性）
3. 局部特征增强（提高图标定位精度）
4. 自适应图像预处理
5. 元素类型感知的 Prompt 模板
6. 集成推理策略

用法:
    from gui_agent.grounding.showui_enhanced_grounder import ShowUIEnhancedGrounder
    grounder = ShowUIEnhancedGrounder()
    result = grounder.predict("screenshot.png", "search button")
"""

from __future__ import annotations

import ast
import math
from typing import Any
from collections import Counter

import numpy as np
import torch
from PIL import Image, ImageFilter
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

from gui_agent.grounding.base import BaseGrounder
from gui_agent.schemas import GroundingResult, UIElement

# ── Prompt 模板 ──

_GROUNDING_SYSTEM = (
    "Based on the screenshot of the page, I give a text description "
    "and you give its corresponding location. The coordinate represents "
    "a clickable location [x, y] for an element, which is a relative "
    "coordinate on the screenshot, scaled from 0 to 1."
)

_ICON_GROUNDING_SYSTEM = (
    "Based on the screenshot of the page, I give a description of an icon "
    "or graphical element. Focus on finding the exact icon location. "
    "The coordinate represents a clickable location [x, y] for the element, "
    "which is a relative coordinate on the screenshot, scaled from 0 to 1. "
    "Pay attention to small icons, toolbar buttons, and graphical elements."
)

_TEXT_GROUNDING_SYSTEM = (
    "Based on the screenshot of the page, I give a text description of a "
    "text element. Locate the exact text on the screen. "
    "The coordinate represents a clickable location [x, y] for the element, "
    "which is a relative coordinate on the screenshot, scaled from 0 to 1."
)

# 图片分辨率参数
_MIN_PIXELS = 256 * 28 * 28
_MAX_PIXELS = 1344 * 28 * 28


def _is_icon_query(query: str) -> bool:
    """判断查询是否可能是图标类型。"""
    icon_keywords = [
        "icon", "logo", "avatar", "profile", "setting", "gear",
        "menu", "hamburger", "share", "like", "heart", "star",
        "bookmark", "flag", "trash", "delete", "close", "x",
        "plus", "add", "minus", "zoom", "search", "magnifier",
        "home", "house", "user", "person", "cart", "shopping",
        "bell", "notification", "mail", "envelope", "camera",
        "photo", "image", "play", "pause", "stop", "refresh",
        "sync", "upload", "download", "arrow", "chevron",
        "thumb", "upvote", "downvote", "more", "ellipsis",
        "grid", "list", "view", "filter", "sort",
        "full screen", "maximize", "minimize",
    ]
    query_lower = query.lower()
    return any(kw in query_lower for kw in icon_keywords)


def _classify_query(query: str) -> str:
    """分类查询类型: 'icon', 'text', 'general'"""
    if _is_icon_query(query):
        return "icon"
    # 如果包含文本相关关键词
    text_keywords = ["text", "label", "title", "heading", "paragraph",
                     "write", "type", "input", "enter", "fill",
                     "search", "find", "check", "read"]
    query_lower = query.lower()
    if any(kw in query_lower for kw in text_keywords):
        return "text"
    return "general"


def _get_system_prompt(query: str) -> str:
    """根据查询类型选择最佳 prompt。"""
    qtype = _classify_query(query)
    if qtype == "icon":
        return _ICON_GROUNDING_SYSTEM
    elif qtype == "text":
        return _TEXT_GROUNDING_SYSTEM
    return _GROUNDING_SYSTEM


class ShowUIEnhancedGrounder(BaseGrounder):
    """ShowUI-2B 定位能力增强版。

    通过对 ShowUI-2B 添加后处理、多尺度推理、局部增强等策略，
    在不修改模型权重的前提下提升定位准确率。

    Args:
        model_name: ShowUI 模型名称或路径
        device: 推理设备
        confidence_threshold: 置信度阈值
        max_new_tokens: 生成的最大 token 数
        use_multiscale: 是否启用多尺度推理
        use_local_refine: 是否启用局部特征增强
        use_adaptive_prompt: 是否使用自适应 prompt
        edge_buffer: 边缘缓冲比例
        multiscale_scales: 多尺度推理的缩放比例列表
    """

    def __init__(
        self,
        model_name: str = "showlab/ShowUI-2B",
        device: str = "cuda",
        confidence_threshold: float = 0.0,
        max_new_tokens: int = 128,
        use_multiscale: bool = False,
        use_local_refine: bool = False,
        use_adaptive_prompt: bool = True,
        edge_buffer: float = 0.005,
        multiscale_scales: list[float] | None = None,
    ) -> None:
        """初始化增强版 Grounder。

        默认仅启用自适应 Prompt（零额外推理成本），
        多尺度和局部增强需要额外推理调用，默认关闭。
        """
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.confidence_threshold = confidence_threshold
        self.max_new_tokens = max_new_tokens
        self.use_multiscale = use_multiscale
        self.use_local_refine = use_local_refine
        self.use_adaptive_prompt = use_adaptive_prompt
        self.edge_buffer = edge_buffer
        self.multiscale_scales = multiscale_scales or [0.7, 1.0, 1.3]

        print(f"加载 ShowUI-2B（增强版）...")
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )
        self.processor = AutoProcessor.from_pretrained(
            model_name,
            min_pixels=_MIN_PIXELS,
            max_pixels=_MAX_PIXELS,
        )
        self.model.eval()

        features = []
        if self.use_multiscale:
            features.append(f"多尺度({self.multiscale_scales})")
        if self.use_local_refine:
            features.append("局部增强")
        if self.use_adaptive_prompt:
            features.append("自适应Prompt")
        print(f"  ✓ ShowUI-2B 增强版加载完成（{', '.join(features)}）")

        self._metadata = {
            "source": "showui_enhanced_grounder",
            "model": model_name,
        }

    # ── 主推理入口 ──

    @torch.no_grad()
    def predict(
        self,
        screenshot_path: str,
        query: str,
        elements: list[UIElement] | None = None,
        dom_text: str | None = None,
    ) -> GroundingResult:
        """定位指定元素（增强版）。

        集成多尺度推理、局部特征增强、坐标后处理等优化策略。

        Args:
            screenshot_path: 截图文件路径
            query: 指令文本，如 "search button"
            elements: 可选 DOM 元素列表，用于交叉验证
            dom_text: 可选 DOM 文本
        Returns:
            GroundingResult: 定位结果
        """
        image = Image.open(screenshot_path).convert("RGB")
        orig_w, orig_h = image.size

        # Step 1: 多尺度推理（如果启用）
        if self.use_multiscale:
            multiscale_pred = self._predict_multiscale(image, query)
        else:
            multiscale_pred = None

        # Step 2: 单尺度基准预测
        base_pred = self._predict_single(image, query)

        # Step 3: 坐标融合
        if multiscale_pred is not None:
            fused_pred = self._fuse_predictions([base_pred, multiscale_pred])
        else:
            fused_pred = base_pred

        # Step 4: 局部特征增强（如果启用）
        if self.use_local_refine and fused_pred is not None:
            refined_pred = self._refine_with_local_crop(image, fused_pred, query)
            if refined_pred is not None:
                fused_pred = self._fuse_predictions([fused_pred, refined_pred])

        # Step 5: 坐标后处理
        final_point = self._postprocess_coordinate(fused_pred, (orig_w, orig_h))

        # Step 6: DOM 交叉验证（如果提供 DOM 元素）
        if final_point is not None and elements:
            dom_refined = self._refine_with_dom(final_point, elements)
            if dom_refined is not None:
                final_point = dom_refined["point"]

        # 构建结果
        if final_point is not None:
            result = GroundingResult(
                query=query,
                point=final_point,
                bbox=None,
                score=1.0,
                metadata={
                    **self._metadata,
                    "base_pred": base_pred,
                    "multiscale_used": self.use_multiscale,
                    "local_refine_used": self.use_local_refine,
                    "adaptive_prompt_used": self.use_adaptive_prompt,
                },
            )
        else:
            result = GroundingResult(
                query=query, point=None, bbox=None, score=0.0,
                metadata={**self._metadata, "error": "prediction_failed"},
            )

        return result

    # ── 内部推理方法 ──

    @torch.no_grad()
    def _predict_single(
        self, image: Image.Image, query: str
    ) -> list[float] | None:
        """单次推理，返回归一化坐标 [x, y] 或 None。"""
        prompt = _get_system_prompt(query) if self.use_adaptive_prompt else _GROUNDING_SYSTEM

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image",
                        "image": image,
                        "min_pixels": _MIN_PIXELS,
                        "max_pixels": _MAX_PIXELS,
                    },
                    {"type": "text", "text": query},
                ],
            }
        ]

        try:
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
            )
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
            )
            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
            ]
            output_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )[0]

            return self._parse_coordinate(output_text)
        except Exception:
            return None

    def _parse_coordinate(self, text: str) -> list[float] | None:
        """解析模型输出的坐标文本。"""
        try:
            point = ast.literal_eval(text.strip())
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return None
            return [float(point[0]), float(point[1])]
        except Exception:
            return None

    # ── 多尺度推理 ──

    def _predict_multiscale(
        self, image: Image.Image, query: str
    ) -> list[float] | None:
        """多尺度推理：在不同缩放比例下分别预测，融合结果。"""
        orig_w, orig_h = image.size
        predictions = []
        confidences = []

        for scale in self.multiscale_scales:
            # 缩放图像
            new_w = max(224, int(orig_w * scale))
            new_h = max(224, int(orig_h * scale))
            scaled_img = image.resize((new_w, new_h), Image.LANCZOS)

            pred = self._predict_single(scaled_img, query)
            if pred is not None:
                # 映射回原始坐标空间
                pred_mapped = [pred[0], pred[1]]
                predictions.append(pred_mapped)
                # 使用 1.0 作为基础置信度（后续可结合模型 logits）
                confidences.append(1.0)

        if len(predictions) < 1:
            return None

        # 过滤离群点
        valid = self._filter_outlier_predictions(predictions)
        if len(valid) < 1:
            return predictions[0]  # 如果全部被过滤，返回第一个

        # 加权平均
        weights = [1.0 / len(valid)] * len(valid)  # 等权重
        fused_x = sum(p[0] * w for p, w in zip(valid, weights))
        fused_y = sum(p[1] * w for p, w in zip(valid, weights))

        return [fused_x, fused_y]

    def _filter_outlier_predictions(
        self, predictions: list[list[float]]
    ) -> list[list[float]]:
        """使用 IQR 方法过滤离群预测点。"""
        if len(predictions) <= 2:
            return predictions

        xs = [p[0] for p in predictions]
        ys = [p[1] for p in predictions]

        def _filter_outliers_1d(values):
            q1 = np.percentile(values, 25)
            q3 = np.percentile(values, 75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            return [lower <= v <= upper for v in values]

        x_mask = _filter_outliers_1d(xs)
        y_mask = _filter_outliers_1d(ys)
        mask = [a and b for a, b in zip(x_mask, y_mask)]

        return [p for p, m in zip(predictions, mask) if m]

    # ── 局部特征增强 ──

    def _refine_with_local_crop(
        self, image: Image.Image, initial_pred: list[float], query: str
    ) -> list[float] | None:
        """在预测点周围做局部放大，精确定位。"""
        w, h = image.size
        cx, cy = initial_pred[0] * w, initial_pred[1] * h

        # 动态裁剪尺寸：根据图像大小调整
        crop_ratio = 0.4  # 裁剪区域占图像比例
        crop_size = int(min(w, h) * crop_ratio)
        crop_size = max(100, min(crop_size, 800))  # 限制范围

        x1 = max(0, int(cx - crop_size / 2))
        y1 = max(0, int(cy - crop_size / 2))
        x2 = min(w, x1 + crop_size)
        y2 = min(h, y1 + crop_size)

        # 确保裁剪区域有效
        if x2 - x1 < 50 or y2 - y1 < 50:
            return None

        crop = image.crop((x1, y1, x2, y2))
        local_pred = self._predict_single(crop, query)

        if local_pred is None:
            return None

        # 映射回全局坐标
        global_x = (x1 + local_pred[0] * (x2 - x1)) / w
        global_y = (y1 + local_pred[1] * (y2 - y1)) / h

        return [global_x, global_y]

    # ── 坐标后处理 ──

    def _postprocess_coordinate(
        self, point: list[float] | None, img_size: tuple[int, int]
    ) -> list[float] | None:
        """坐标后处理：轻量化边界约束。

        原则：尽量保持原始预测不变，只修复明显异常的坐标。
        - 只对极端边缘值（< 0.001 或 > 0.999）做裁剪
        - 不做中心偏置校正（避免影响正确预测）
        """
        if point is None:
            return None

        x, y = point

        # 只对极端值做裁剪（防止 OUT_OF_BOUNDS）
        x = max(0.001, min(0.999, x))
        y = max(0.001, min(0.999, y))

        return [round(x, 4), round(y, 4)]

    # ── 预测融合 ──

    def _fuse_predictions(
        self, predictions: list[list[float] | None]
    ) -> list[float] | None:
        """融合多个预测结果。"""
        valid = [p for p in predictions if p is not None]
        if not valid:
            return None
        if len(valid) == 1:
            return valid[0]

        # 过滤离群点
        filtered = self._filter_outlier_predictions(valid)
        if not filtered:
            filtered = valid

        # 取中位数（对离群点更鲁棒）
        xs = [p[0] for p in filtered]
        ys = [p[1] for p in filtered]
        return [float(np.median(xs)), float(np.median(ys))]

    # ── DOM 交叉验证 ──

    def _refine_with_dom(
        self, point: list[float], elements: list[UIElement]
    ) -> dict | None:
        """DOM 交叉验证：检查预测点是否落在某个 DOM 元素内。"""
        px, py = point
        best_match = None
        best_area = float("inf")

        for elem in elements:
            x1, y1, x2, y2 = elem.bbox
            if x1 <= px <= x2 and y1 <= py <= y2:
                area = (x2 - x1) * (y2 - y1)
                if area < best_area:
                    best_area = area
                    best_match = {
                        "point": elem.center,
                        "element_id": elem.element_id,
                        "ref": elem.ref,
                        "text": elem.text,
                    }

        return best_match

    # ── 评测辅助方法 ──

    def predict_batch(
        self,
        image_paths: list[str],
        queries: list[str],
        batch_size: int = 4,
    ) -> list[GroundingResult]:
        """批量预测（逐条推理，无 batch 优化）。"""
        results = []
        for img_path, query in zip(image_paths, queries):
            result = self.predict(screenshot_path=img_path, query=query)
            results.append(result)
        return results

    def get_metadata(self) -> dict:
        """返回当前配置的元信息。"""
        return {
            **self._metadata,
            "use_multiscale": self.use_multiscale,
            "use_local_refine": self.use_local_refine,
            "use_adaptive_prompt": self.use_adaptive_prompt,
            "edge_buffer": self.edge_buffer,
            "multiscale_scales": self.multiscale_scales,
            "center_bias_correction": self.center_bias_correction,
        }

    def __repr__(self) -> str:
        return (
            f"ShowUIEnhancedGrounder("
            f"multiscale={self.use_multiscale}, "
            f"refine={self.use_local_refine}, "
            f"adaptive_prompt={self.use_adaptive_prompt}"
            f")"
        )