from __future__ import annotations

import json
from typing import Any

from gui_agent.grounding.base import BaseGrounder
from gui_agent.llm.base import BaseChatModel, BaseVisionChatModel, ChatMessage
from gui_agent.policy.base import BasePolicy
from gui_agent.schemas import Action, Observation, UIElement

# 可输入元素的 HTML tag 集合（TYPE 动作优先匹配这些）
_INPUT_TAGS = frozenset({"input", "textarea", "select"})

_VLM_SYSTEM_PROMPT = """\
You are a GUI agent that must reason from the screenshot first. \
Do not rely on hidden DOM information. \
Return only valid JSON using this schema:

{"action":"CLICK|TYPE|SCROLL|STOP",\
"target_text":string|null,\
"target_description":string|null,\
"value":string|null,\
"position":[x,y]|null,\
"scroll":string|null}

CRITICAL: position [x, y] MUST be normalized values between 0.0 and 1.0.
- x=0.0 is left edge, x=1.0 is right edge
- y=0.0 is top edge, y=1.0 is bottom edge
- Example: center of screen = [0.5, 0.5]
- DO NOT output pixel coordinates like [175, 58] — only [0.0-1.0] values.
- If you cannot give normalized coordinates, set position to null and use target_text instead.

Guidelines:
- For TYPE actions, set target_text to the input field description (e.g. "搜索框").
- If a previous step failed (noted in history), try a different approach.
- After navigating to a new page, focus on the current page's content.
- Break the task into sub-steps and track your progress.
"""

_TEXT_SYSTEM_PROMPT = """\
You are a web GUI agent. Return only valid JSON. \
Schema: {"action":"CLICK|TYPE|SCROLL|STOP",\
"target_text":string|null,"value":string|null,"scroll":string|null}.

Guidelines:
- For TYPE actions, set target_text to the input field description.
- Learn from recent step errors and try different approaches.
- After a page change, focus on the current page.
"""


class LLMGroundedPolicy(BasePolicy):
    """Two-stage policy with a three-level grounding fallback chain.

    1. Direct VLM position (VLM outputs [x,y] in the action JSON)
    2. VisualGrounder (VLM-based visual grounding from screenshot)
    3. KeywordGrounder (DOM text matching — original behavior)

    All new parameters are optional with sensible defaults, so existing
    code that constructs LLMGroundedPolicy continues to work unchanged.
    """

    def __init__(
        self,
        grounder: BaseGrounder,
        model: BaseChatModel,
        use_vision: bool = False,
        max_history: int = 5,
        visual_history_count: int = 2,
        visual_grounder: BaseGrounder | None = None,
    ) -> None:
        self.grounder = grounder
        self.model = model
        self.use_vision = use_vision
        self.last_grounding = None
        self.max_history = max_history
        self.visual_history_count = visual_history_count
        self.visual_grounder = visual_grounder

    def act(self, observation: Observation) -> Action:
        self.last_grounding = None

        messages = self._build_messages(observation)

        raw = self._call_model(messages, observation)
        parsed = _parse_json(raw)

        action_type = str(parsed.get("action", "STOP")).upper()
        target_text = parsed.get("target_text")
        target_description = parsed.get("target_description")
        value = parsed.get("value")
        scroll = parsed.get("scroll")
        direct_position = parsed.get("position")
        query = _pick_query(target_text, target_description)

        # ── Three-level fallback chain ──
        point, matched_ref, grounding_score, grounding_source = self._resolve_position(
            action_type=action_type,
            query=query,
            direct_position=direct_position,
            observation=observation,
        )

        # ── Action dispatch ──
        if action_type == "CLICK":
            if point is not None:
                return Action(
                    action="CLICK",
                    position=point,
                    metadata={
                        "ref": matched_ref,
                        "target_text": query,
                        "grounding_score": grounding_score,
                        "grounding_source": grounding_source,
                    },
                )
            return Action(action="STOP", metadata={"reason": "grounding_failed_all_levels"})

        if action_type == "TYPE":
            if not isinstance(value, str):
                return Action(action="STOP", metadata={"reason": "missing_value"})
            return Action(
                action="TYPE",
                value=value,
                position=point,
                metadata={
                    "ref": matched_ref,
                    "target_text": query,
                    "grounding_score": grounding_score,
                    "grounding_source": grounding_source,
                },
            )

        if action_type == "SCROLL":
            direction = "down"
            if isinstance(scroll, str) and scroll.strip():
                direction = scroll.strip().lower()
            return Action(action="SCROLL", value=direction)

        return Action(action="STOP")

    def _resolve_position(
        self,
        action_type: str,
        query: str | None,
        direct_position: Any,
        observation: Observation,
    ) -> tuple[list[float] | None, int | str | None, float, str]:
        """Three-level fallback chain for resolving a click/type position."""
        point: list[float] | None = None
        matched_ref: int | str | None = None
        grounding_score = 0.0
        grounding_source = "none"

        # Level 1: Direct VLM position (highest confidence)
        if action_type in ("CLICK", "TYPE") and direct_position is not None:
            if isinstance(direct_position, (list, tuple)) and len(direct_position) == 2:
                try:
                    raw_x = float(direct_position[0])
                    raw_y = float(direct_position[1])
                    # Auto-normalize pixel coordinates if VLM outputs them despite instructions
                    # If values > 1.5, treat as pixel coords and normalize via screen size
                    if raw_x > 1.5 or raw_y > 1.5:
                        screen_size = observation.metadata.get("screen_size")
                        if screen_size and len(screen_size) == 2:
                            w, h = float(screen_size[0]), float(screen_size[1])
                            if w > 0 and h > 0:
                                raw_x = raw_x / w
                                raw_y = raw_y / h
                        else:
                            # No screen size info — skip direct position, fall to next level
                            pass

                    point = [raw_x, raw_y]
                    grounding_score = 1.0
                    grounding_source = "vlm_direct"
                    self.last_grounding = {
                        "source": "vlm_direct",
                        "point": point,
                        "score": grounding_score,
                    }
                    return point, matched_ref, grounding_score, grounding_source
                except (ValueError, TypeError):
                    pass

        # Level 2: VisualGrounder (VLM description → screenshot coordinates)
        if point is None and query and self.visual_grounder is not None:
            grounding = self.visual_grounder.predict(
                screenshot_path=observation.screenshot_path,
                query=query,
                elements=observation.elements,
                dom_text=observation.dom_text,
            )
            if grounding.score > 0 and grounding.point is not None:
                point = grounding.point
                matched_ref = grounding.matched_ref
                grounding_score = grounding.score
                grounding_source = "visual_grounder"
                self.last_grounding = {
                    "source": "visual_grounder",
                    "point": point,
                    "score": grounding_score,
                    "matched_element": grounding.matched_element_id,
                }
                return point, matched_ref, grounding_score, grounding_source

        # Level 3: KeywordGrounder (DOM text matching — original behavior)
        if point is None and query:
            elements_for_grounding = observation.elements
            if action_type == "TYPE":
                input_els = _filter_input_elements(observation.elements)
                elements_for_grounding = input_els if input_els else observation.elements

            grounding = self.grounder.predict(
                screenshot_path=observation.screenshot_path,
                query=query,
                elements=elements_for_grounding,
                dom_text=observation.dom_text,
            )
            if grounding.point is not None:
                point = grounding.point
                matched_ref = grounding.matched_ref
                grounding_score = grounding.score
                grounding_source = "keyword_grounder"
                self.last_grounding = {
                    "source": "keyword_grounder",
                    "point": point,
                    "score": grounding_score,
                    "matched_element": grounding.matched_element_id,
                }

        return point, matched_ref, grounding_score, grounding_source

    def _call_model(self, messages: list[ChatMessage], observation: Observation) -> str:
        if self.use_vision and isinstance(self.model, BaseVisionChatModel):
            # Collect all screenshot paths (current + visual history)
            image_paths = [observation.screenshot_path]
            if self.visual_history_count > 0 and observation.history:
                hist_paths = [
                    h["screenshot_path"]
                    for h in observation.history[-self.visual_history_count :]
                    if h.get("screenshot_path")
                    and h["screenshot_path"] != observation.screenshot_path
                ]
                image_paths = hist_paths + [observation.screenshot_path]

            if len(image_paths) > 1 and hasattr(self.model, "chat_with_images"):
                return self.model.chat_with_images(messages, image_paths)
            return self.model.chat_with_image(messages, observation.screenshot_path)
        return self.model.chat(messages)

    def _build_messages(self, observation: Observation) -> list[ChatMessage]:
        instruction = observation.task
        history_text = _format_history(observation.history)
        progress_text = observation.metadata.get("progress_summary", "")

        if self.use_vision:
            system = ChatMessage(role="system", content=_VLM_SYSTEM_PROMPT)
            user_content = f"Task: {instruction}\n"
            if history_text:
                user_content += f"Recent steps:\n{history_text}\n"
            if progress_text and "No prior steps" not in progress_text:
                user_content += f"{progress_text}\n"
            user_content += (
                f"Task fields: {_format_fields(observation.fields)}\n"
                "Inspect the screenshot and decide the next GUI action.\n"
                "If clicking or typing, set target_text to the visible label if possible.\n"
                "If there is no exact text label, set target_description to a short visible description.\n"
                "IMPORTANT: position [x,y] must be 0.0-1.0 normalized. NOT pixel coordinates.\n"
                "Return JSON only."
            )
            return [system, ChatMessage(role="user", content=user_content)]

        # Text-only mode
        element_texts = [e.text for e in observation.elements if e.text]
        visible = ", ".join(element_texts[:80])
        system = ChatMessage(role="system", content=_TEXT_SYSTEM_PROMPT)
        user_content = f"Instruction: {instruction}\n"
        if history_text:
            user_content += f"Recent steps:\n{history_text}\n"
        if progress_text and "No prior steps" not in progress_text:
            user_content += f"{progress_text}\n"
        user_content += f"Visible element texts: {visible}\n"
        user_content += "Decide the next action."
        return [system, ChatMessage(role="user", content=user_content)]


def _filter_input_elements(elements: list[UIElement]) -> list[UIElement]:
    """只保留可输入元素（input / textarea / select）。"""
    return [e for e in elements if e.element_type.lower() in _INPUT_TAGS]


def _format_history(history: list[dict[str, Any]] | None) -> str:
    """将执行历史格式化为可读文本。"""
    if not history:
        return ""
    lines: list[str] = []
    for h in history[-5:]:
        action_str = h.get("action", "?")
        value_str = h.get("value", "")
        error_str = h.get("error", "")
        url_str = h.get("url", "")
        line = f"  - {action_str}"
        if value_str:
            line += f' "{value_str[:40]}"'
        if error_str:
            line += f" [ERROR: {error_str[:60]}]"
        if url_str:
            line += f" -> {url_str[:80]}"
        lines.append(line)
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
        return {}


def _format_fields(fields: dict) -> str:
    if not fields:
        return "{}"
    try:
        return json.dumps(fields, ensure_ascii=True)
    except Exception:
        return str(fields)


def _pick_query(target_text: object, target_description: object) -> str | None:
    if isinstance(target_text, str) and target_text.strip():
        return target_text.strip()
    if isinstance(target_description, str) and target_description.strip():
        return target_description.strip()
    return None
