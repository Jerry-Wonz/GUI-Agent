from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class UIElement:
    element_id: str
    text: str
    element_type: str
    bbox: list[float]
    ref: int | str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> list[float]:
        x1, y1, x2, y2 = self.bbox
        return [round((x1 + x2) / 2, 4), round((y1 + y2) / 2, 4)]


@dataclass
class Observation:
    task: str
    screenshot_path: str
    dom_text: str | None = None
    elements: list[UIElement] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["elements"] = [asdict(elem) for elem in self.elements]
        return data


@dataclass
class Action:
    action: str
    value: str | None = None
    position: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundingResult:
    query: str
    point: list[float] | None
    bbox: list[float] | None
    score: float
    matched_element_id: str | None = None
    matched_ref: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StepRecord:
    step_id: int
    task: str
    observation: dict[str, Any]
    grounding: dict[str, Any] | None
    action: dict[str, Any]
    reward: float
    terminated: bool
    info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
