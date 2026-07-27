"""ShowUIGrounder — 基于 ShowUI-2B 的 GUI 定位与导航器。

支持两种模式：
- grounding: 根据文本描述定位元素坐标（默认）
- navigation: 根据任务指令 + 截图 + 历史，输出下一步动作

实现 BaseGrounder 接口，可直接替换 VisualGrounder 用于 Agent 循环。
"""

from __future__ import annotations

import ast
import json
from typing import Any

import torch
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

from gui_agent.grounding.base import BaseGrounder
from gui_agent.schemas import GroundingResult, UIElement

# OCR 辅助（可选）
_OCR_AVAILABLE = False
try:
    from gui_agent.grounding.ocr_helper import OCRHelper
    _OCR_AVAILABLE = True
except ImportError:
    pass

# ── Prompt 模板 ──

_GROUNDING_SYSTEM = (
    "Based on the screenshot of the page, I give a text description "
    "and you give its corresponding location. The coordinate represents "
    "a clickable location [x, y] for an element, which is a relative "
    "coordinate on the screenshot, scaled from 0 to 1."
)

_NAV_WEB_ACTION_SPACE = """
1. `CLICK`: Click on an element, value is not applicable and the position [x,y] is required.
2. `INPUT`: Type a string into an element, value is a string to type and the position [x,y] is required.
3. `SELECT`: Select a value for an element, value is not applicable and the position [x,y] is required.
4. `HOVER`: Hover on an element, value is not applicable and the position [x,y] is required.
5. `ANSWER`: Answer the question, value is the answer and the position is not applicable.
6. `ENTER`: Enter operation, value and position are not applicable.
7. `SCROLL`: Scroll the screen, value is the direction to scroll and the position is not applicable.
8. `SELECT_TEXT`: Select some text content, value is not applicable and position [[x1,y1],[x2,y2]] is the start and end position of the select operation.
9. `COPY`: Copy the text, value is the text to copy and the position is not applicable.
"""

_NAV_PHONE_ACTION_SPACE = """
1. `INPUT`: Type a string into an element, value is a string to type and the position [x,y] is required.
2. `SWIPE`: Swipe the screen, value is not applicable and the position [[x1,y1],[x2,y2]] is the start and end position of the swipe operation.
3. `TAP`: Tap on an element, value is not applicable and the position [x,y] is required.
4. `ANSWER`: Answer the question, value is the status (e.g., 'task complete') and the position is not applicable.
5. `ENTER`: Enter operation, value and position are not applicable.
"""

_NAV_SYSTEM_TEMPLATE = """You are an assistant trained to navigate the {device} screen. Given a task instruction, a screen observation, and an action history sequence, output the next action and wait for the next observation.

Here is the action space:
{action_space}

Format the action as a dictionary with the following keys:
{{'action': 'ACTION_TYPE', 'value': 'element', 'position': [x,y]}}

If value or position is not applicable, set it as `None`.
Position might be [[x1,y1],[x2,y2]] if the action requires a start and end position.
Position represents the relative coordinates on the screenshot and should be scaled to a range of 0-1."""

_NAV_FORMAT_EXAMPLE = """
Example output:
{{'action': 'CLICK', 'value': None, 'position': [0.49, 0.42]}}

For multi-step tasks, output one action at a time. Wait for the next observation after each action."""

# 图片分辨率参数（与 ShowUI 训练时一致）
_MIN_PIXELS = 256 * 28 * 28
_MAX_PIXELS = 1344 * 28 * 28

_ACTION_SPACES = {
    "web": _NAV_WEB_ACTION_SPACE,
    "phone": _NAV_PHONE_ACTION_SPACE,
}


class ShowUIGrounder(BaseGrounder):
    """基于 ShowUI-2B 的 GUI 定位与导航器。

    Args:
        model_name: ShowUI 模型名称或路径
        device: 推理设备
        confidence_threshold: 置信度阈值
        max_new_tokens: 生成的最大 token 数
        mode: 运行模式，"grounding" 或 "navigation"
    """

    def __init__(
        self,
        model_name: str = "showlab/ShowUI-2B",
        device: str = "cuda",
        confidence_threshold: float = 0.0,
        max_new_tokens: int = 128,
        mode: str = "grounding",
        use_ocr: bool = False,
    ) -> None:
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.confidence_threshold = confidence_threshold
        self.max_new_tokens = max_new_tokens
        self.mode = mode
        self.use_ocr = use_ocr and _OCR_AVAILABLE
        self._ocr_helper = None

        print(f"加载 ShowUI-2B（{model_name}）...")
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
        features = [f"模式: {mode}"]
        if self.use_ocr:
            features.append("OCR 辅助")
        print(f"  ✓ ShowUI-2B 加载完成（设备: {self.model.device}, {', '.join(features)}）")

        self._metadata = {
            "source": "showui_grounder",
            "model": model_name,
            "mode": mode,
        }

    # ── 统一推理入口 ──

    @torch.no_grad()
    def predict(
        self,
        screenshot_path: str,
        query: str,
        elements: list[UIElement] | None = None,
        dom_text: str | None = None,
    ) -> GroundingResult:
        """定位指定元素（Grounding 模式）。

        当提供 DOM elements 时，会对 ShowUI 输出做 DOM 交叉验证：
        取包含 ShowUI 预测点的 DOM 元素中心坐标，精度更高。

        Args:
            screenshot_path: 截图文件路径
            query: 指令文本，如 "search button"
            elements: 可选 DOM 元素列表，用于交叉验证
            dom_text: 可选 DOM 文本（暂未使用）
        Returns:
            GroundingResult: 定位结果
        """
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _GROUNDING_SYSTEM},
                    {
                        "type": "image",
                        "image": screenshot_path,
                        "min_pixels": _MIN_PIXELS,
                        "max_pixels": _MAX_PIXELS,
                    },
                    {"type": "text", "text": query},
                ],
            }
        ]
        output_text = self._infer(messages)
        result = self._parse_grounding_result(output_text, query)

        # DOM 交叉验证：如果 ShowUI 预测点在某个 DOM 元素内，取该元素中心坐标
        if result.point is not None and elements:
            dom_refined = self._refine_with_dom(result.point, elements)
            if dom_refined is not None:
                result = GroundingResult(
                    query=result.query,
                    point=dom_refined["point"],
                    bbox=None,
                    score=result.score,
                    matched_element_id=dom_refined["element_id"],
                    matched_ref=dom_refined["ref"],
                    metadata={
                        **result.metadata,
                        "dom_refined": True,
                        "dom_element_text": dom_refined["text"][:50],
                    },
                )

        # OCR 辅助验证：仅验证文本存在，不覆盖 ShowUI 坐标
        if result.point is not None and self.use_ocr:
            ocr_result = self._ocr_check(screenshot_path, query, result.point)
            extra = {"ocr_confirmed": False}
            if ocr_result is not None:
                extra = {"ocr_confirmed": True, "ocr_text": ocr_result["text"][:50]}
            result = GroundingResult(
                query=result.query, point=result.point, bbox=result.bbox,
                score=result.score, matched_element_id=result.matched_element_id,
                matched_ref=result.matched_ref,
                metadata={**result.metadata, **extra},
            )

        return result

    # ── Navigation 模式 ──

    @torch.no_grad()
    def predict_action(
        self,
        screenshot_path: str,
        task: str,
        device_type: str = "web",
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """预测下一步动作（Navigation 模式）。

        Args:
            screenshot_path: 当前截图路径
            task: 任务描述，如 "Search for AI"
            device_type: 设备类型，"web" 或 "phone"
            history: 动作历史列表
        Returns:
            动作字典: {"action": str, "value": str | None, "position": list | None}
        """
        system_prompt = _NAV_SYSTEM_TEMPLATE.format(
            device=device_type,
            action_space=_ACTION_SPACES.get(device_type, _ACTION_SPACES["web"]),
        ) + _NAV_FORMAT_EXAMPLE

        # 构建消息
        content = [
            {"type": "text", "text": system_prompt},
            {"type": "text", "text": f"Task: {task}"},
            {
                "type": "image",
                "image": screenshot_path,
                "min_pixels": _MIN_PIXELS,
                "max_pixels": _MAX_PIXELS,
            },
        ]

        # 添加历史上下文
        if history:
            history_text = "Action history:\n"
            for h in history[-3:]:
                action = h.get("action", "?")
                value = h.get("value", "")
                pos = h.get("position", None)
                history_text += f"  - {action}"
                if value:
                    history_text += f' value="{value}"'
                if pos:
                    history_text += f" position={pos}"
                history_text += "\n"
            content.append({"type": "text", "text": history_text})

        messages = [{"role": "user", "content": content}]
        output_text = self._infer(messages)
        return self._parse_action_result(output_text)

    # ── 内部方法 ──

    @torch.no_grad()
    def _infer(self, messages: list[dict]) -> str:
        """执行模型推理，返回生成的文本。"""
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
        return self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

    def _parse_grounding_result(self, output_text: str, query: str) -> GroundingResult:
        """解析 Grounding 输出。"""
        try:
            point = ast.literal_eval(output_text.strip())
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                return GroundingResult(
                    query=query, point=None, bbox=None, score=0.0,
                    metadata={**self._metadata, "error": f"unexpected: {output_text[:100]}"},
                )
            x = max(0.0, min(1.0, float(point[0])))
            y = max(0.0, min(1.0, float(point[1])))
            return GroundingResult(
                query=query, point=[round(x, 4), round(y, 4)], bbox=None, score=1.0,
                metadata={**self._metadata, "raw_output": output_text.strip()[:100]},
            )
        except Exception as exc:
            return GroundingResult(
                query=query, point=None, bbox=None, score=0.0,
                metadata={**self._metadata, "error": str(exc)[:200]},
            )

    def _parse_action_result(self, output_text: str) -> dict[str, Any]:
        """解析 Navigation 输出。"""
        text = output_text.strip()
        # 尝试解析 JSON 字典
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试解析 Python 字典字面量
        try:
            result = ast.literal_eval(text)
            if isinstance(result, dict):
                return result
            if isinstance(result, (list, tuple)):
                return result[0] if result else {"action": "STOP"}
        except (SyntaxError, ValueError):
            pass
        # 尝试从文本中提取第一个 { ... }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                result = ast.literal_eval(text[start:end + 1])
                if isinstance(result, dict):
                    return result
            except (SyntaxError, ValueError):
                pass
        return {"action": "STOP", "value": None, "position": None}

    def _get_ocr(self) -> OCRHelper | None:
        """懒加载 OCR 实例。"""
        if self._ocr_helper is None and self.use_ocr:
            self._ocr_helper = OCRHelper()
        return self._ocr_helper

    def _ocr_check(
        self, image_path: str, query: str, point: list[float],
    ) -> dict | None:
        """OCR 辅助验证：检查预测点附近是否有匹配文本。"""
        ocr = self._get_ocr()
        if ocr is None:
            return None

        # 先在预测点附近搜索
        match = ocr.match_text_at_point(image_path, query, point)
        if match is not None:
            bbox = match["bbox"]
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            return {"point": [round(cx, 4), round(cy, 4)], "bbox": bbox, "text": match["text"]}

        # 附近未匹配，全页搜索
        matches = ocr.search_text_on_page(image_path, query)
        if matches:
            m = matches[0]
            bbox = m["bbox"]
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            return {"point": [round(cx, 4), round(cy, 4)], "bbox": bbox, "text": m["text"]}

        return None

    def _refine_with_dom(
        self, point: list[float], elements: list[UIElement]
    ) -> dict | None:
        """DOM 交叉验证：检查 ShowUI 预测点是否落在某个 DOM 元素内。

        如果找到匹配元素，返回该元素的中心坐标（更精确）。
        否则返回 None（保持 ShowUI 原始坐标）。

        Args:
            point: ShowUI 预测的归一化坐标 [x, y]
            elements: DOM 元素列表
        Returns:
            dict: {"point": [x, y], "element_id": str, "ref": int|str, "text": str} 或 None
        """
        px, py = point
        best_match = None
        best_area = float("inf")  # 优先选面积最小的包含元素（最精确）

        for elem in elements:
            x1, y1, x2, y2 = elem.bbox  # 归一化 [0, 1] 坐标
            if x1 <= px <= x2 and y1 <= py <= y2:
                # 计算元素面积
                area = (x2 - x1) * (y2 - y1)
                if area < best_area:
                    best_area = area
                    center = elem.center  # 使用 UIElement 的 center 属性
                    best_match = {
                        "point": center,
                        "element_id": elem.element_id,
                        "ref": elem.ref,
                        "text": elem.text,
                    }

        return best_match