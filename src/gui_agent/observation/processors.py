from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from gui_agent.schemas import Observation, UIElement
from gui_agent.utils.io import ensure_dir


def normalize_bbox(
    raw_element: dict[str, Any],
    screen_size: tuple[int, int] | None = None,
) -> list[float]:
    """Normalize element geometry into [x1, y1, x2, y2]."""
    if "bbox" in raw_element and raw_element["bbox"]:
        bbox = raw_element["bbox"]
        if len(bbox) == 4:
            normalized = [float(value) for value in bbox]
            return _normalize_by_screen_size(normalized, screen_size)

    left = raw_element.get("left", raw_element.get("x", 0))
    top = raw_element.get("top", raw_element.get("y", 0))
    width = raw_element.get("width", raw_element.get("w", 0))
    height = raw_element.get("height", raw_element.get("h", 0))

    if raw_element.get("right") is not None and raw_element.get("bottom") is not None:
        normalized = [
            float(left),
            float(top),
            float(raw_element["right"]),
            float(raw_element["bottom"]),
        ]
        return _normalize_by_screen_size(normalized, screen_size)

    normalized = [
        float(left),
        float(top),
        float(left) + float(width),
        float(top) + float(height),
    ]
    return _normalize_by_screen_size(normalized, screen_size)


def build_ui_elements(
    raw_elements: Iterable[dict[str, Any]],
    screen_size: tuple[int, int] | None = None,
) -> list[UIElement]:
    elements: list[UIElement] = []
    for index, raw_element in enumerate(raw_elements):
        element_id = str(raw_element.get("element_id", raw_element.get("id", raw_element.get("ref", index))))
        text = str(raw_element.get("text", raw_element.get("value", raw_element.get("label", ""))))
        element_type = str(raw_element.get("tag", raw_element.get("type", "unknown")))
        ref = raw_element.get("ref")
        # 把所有额外字段放入 attributes，包括 placeholder / aria_label / role / input_type / name
        attributes = {
            key: value
            for key, value in raw_element.items()
            if key not in {"bbox", "left", "top", "width", "height", "x", "y", "w", "h"}
        }
        elements.append(
            UIElement(
                element_id=element_id,
                text=text,
                element_type=element_type,
                bbox=normalize_bbox(raw_element, screen_size=screen_size),
                ref=ref,
                attributes=attributes,
            )
        )
    return elements


def _normalize_by_screen_size(
    bbox: list[float],
    screen_size: tuple[int, int] | None,
) -> list[float]:
    if not screen_size:
        return bbox

    width, height = screen_size
    if width <= 0 or height <= 0:
        return bbox

    if all(0.0 <= value <= 1.0 for value in bbox):
        return bbox

    x1, y1, x2, y2 = bbox
    return [
        round(x1 / width, 6),
        round(y1 / height, 6),
        round(x2 / width, 6),
        round(y2 / height, 6),
    ]


def build_dom_text(elements: list[UIElement]) -> str:
    return " ".join(element.text for element in elements if element.text).strip()


def save_rgb_image(
    image: Any,
    output_dir: str | Path,
    filename: str,
) -> str:
    """
    Save a numpy-like RGB array to a portable PPM file without extra dependencies.
    """
    output_dir = ensure_dir(output_dir)
    file_path = output_dir / filename

    try:
        height, width = image.shape[0], image.shape[1]
        pixels = image.tolist()
    except Exception as exc:  # pragma: no cover - best-effort fallback
        raise ValueError("Unsupported screenshot array format.") from exc

    with file_path.open("wb") as fh:
        fh.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
        for row in pixels:
            for pixel in row:
                fh.write(bytes(int(channel) for channel in pixel[:3]))

    return str(file_path)


def build_observation(
    *,
    task: str,
    screenshot_path: str,
    elements: list[UIElement],
    history: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    dom_text: str | None = None,
    fields: dict[str, Any] | None = None,
) -> Observation:
    return Observation(
        task=task,
        screenshot_path=screenshot_path,
        dom_text=dom_text if dom_text is not None else build_dom_text(elements),
        elements=elements,
        history=list(history or []),
        metadata=dict(metadata or {}),
        fields=dict(fields or {}),
    )
