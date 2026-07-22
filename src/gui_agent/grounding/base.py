from __future__ import annotations

from abc import ABC, abstractmethod

from gui_agent.schemas import GroundingResult, UIElement


class BaseGrounder(ABC):
    @abstractmethod
    def predict(
        self,
        screenshot_path: str,
        query: str,
        elements: list[UIElement] | None = None,
        dom_text: str | None = None,
    ) -> GroundingResult:
        raise NotImplementedError
