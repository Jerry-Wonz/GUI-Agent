from __future__ import annotations

import json
import re
from typing import Any

from gui_agent.grounding.base import BaseGrounder
from gui_agent.llm.base import BaseVisionChatModel, ChatMessage
from gui_agent.schemas import GroundingResult, UIElement

_DEFAULT_PROMPT = """\
You are a GUI element locator. Given a screenshot of a web page and a \
description of a UI element, output the normalized center coordinates \
[x, y] (each between 0 and 1) of that element.

Rules:
- x=0.0 is left edge, x=1.0 is right edge
- y=0.0 is top edge, y=1.0 is bottom edge
- If the element has a clear bounding box, include bbox: [x1,y1,x2,y2]
- Set confidence between 0.0 (not sure) and 1.0 (very sure)
- Output ONLY valid JSON, no other text

Query: "{query}"
"""


class VisualGrounder(BaseGrounder):
    """A vision-based grounding module that uses a VLM to locate UI elements
    directly from screenshots.

    This implements the core ShowUI insight: a VLM that sees a screenshot
    can predict click coordinates directly from visual features, bypassing
    brittle DOM text matching.

    Falls back gracefully when the VLM cannot locate the element.
    """

    def __init__(
        self,
        vlm_model: BaseVisionChatModel,
        confidence_threshold: float = 0.3,
        prompt_template: str | None = None,
    ) -> None:
        self._vlm = vlm_model
        self.confidence_threshold = confidence_threshold
        self.prompt_template = prompt_template or _DEFAULT_PROMPT

    def predict(
        self,
        screenshot_path: str,
        query: str,
        elements: list[UIElement] | None = None,
        dom_text: str | None = None,
    ) -> GroundingResult:
        # 1. Build VLM prompt
        user_prompt = self.prompt_template.format(query=query)
        messages = [ChatMessage(role="user", content=user_prompt)]

        # 2. Call VLM with screenshot
        try:
            raw_response = self._vlm.chat_with_image(messages, screenshot_path)
        except Exception:
            return GroundingResult(
                query=query,
                point=None,
                bbox=None,
                score=0.0,
                metadata={"source": "visual_grounder", "error": "vlm_call_failed"},
            )

        # 3. Parse JSON from response
        parsed = _parse_coordinate_json(raw_response)
        if parsed is None:
            return GroundingResult(
                query=query,
                point=None,
                bbox=None,
                score=0.0,
                metadata={
                    "source": "visual_grounder",
                    "error": "parse_failed",
                    "raw": raw_response[:200],
                },
            )

        point = parsed.get("point")
        bbox = parsed.get("bbox")
        confidence = parsed.get("confidence", 0.5)

        # 4. Validate coordinates
        point = _validate_point(point)
        bbox = _validate_bbox(bbox)

        if point is None:
            return GroundingResult(
                query=query,
                point=None,
                bbox=None,
                score=0.0,
                metadata={"source": "visual_grounder", "error": "invalid_coordinates"},
            )

        # 5. Consistency check against DOM elements (if available)
        score = float(confidence)
        matched_element_id = None
        matched_ref = None

        if elements:
            point_in_element = _find_containing_element(point, elements)
            if point_in_element is not None:
                # Boost confidence: VLM prediction aligns with a real DOM element
                score = min(1.0, score * 1.1)
                matched_element_id = point_in_element.element_id
                matched_ref = point_in_element.ref
            else:
                # Penalty: prediction doesn't align with any known element
                score *= 0.8

        # Apply threshold
        if score < self.confidence_threshold:
            return GroundingResult(
                query=query,
                point=None,
                bbox=None,
                score=round(score, 4),
                metadata={
                    "source": "visual_grounder",
                    "error": "below_confidence_threshold",
                },
            )

        return GroundingResult(
            query=query,
            point=point,
            bbox=bbox,
            score=round(score, 4),
            matched_element_id=matched_element_id,
            matched_ref=matched_ref,
            metadata={"source": "visual_grounder", "confidence": confidence},
        )


# ── Helpers ──


def _parse_coordinate_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from VLM response, tolerating markdown fences."""
    text = text.strip()
    # Remove markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {…} block
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return None


def _validate_point(point: Any) -> list[float] | None:
    """Validate and clamp [x, y] coordinates to [0, 1]."""
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    try:
        x = max(0.0, min(1.0, float(point[0])))
        y = max(0.0, min(1.0, float(point[1])))
        return [round(x, 4), round(y, 4)]
    except (ValueError, TypeError):
        return None


def _validate_bbox(bbox: Any) -> list[float] | None:
    """Validate [x1, y1, x2, y2] bounding box."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        values = [max(0.0, min(1.0, float(v))) for v in bbox]
        return [round(v, 4) for v in values]
    except (ValueError, TypeError):
        return None


def _find_containing_element(
    point: list[float],
    elements: list[UIElement],
) -> UIElement | None:
    """Find the first element whose bounding box contains the given point."""
    px, py = point
    for elem in elements:
        x1, y1, x2, y2 = elem.bbox
        if x1 <= px <= x2 and y1 <= py <= y2:
            return elem
    return None
