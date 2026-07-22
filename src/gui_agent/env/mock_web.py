from __future__ import annotations

from gui_agent.env.base import BaseWebEnv
from gui_agent.observation.processors import build_observation
from gui_agent.schemas import Action, Observation, UIElement


class MockWebEnv(BaseWebEnv):
    """A deterministic mock environment for end-to-end agent loop testing."""

    def __init__(self) -> None:
        self.task = "在页面中搜索 ThinkPad 并打开 Lenovo ThinkPad X1 Carbon"
        self.query = "ThinkPad"
        self.target_result = "Lenovo ThinkPad X1 Carbon"
        self.stage = "search"
        self.history: list[dict] = []
        self.search_submitted = False

    def reset(self) -> Observation:
        self.stage = "search"
        self.history = []
        self.search_submitted = False
        return self._build_observation()

    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        reward = 0.0
        terminated = False
        info = {"success": False, "stage": self.stage}

        self.history.append(action.to_dict())

        if self.stage == "search":
            if action.action == "TYPE" and action.value == self.query:
                reward = 0.2
            elif action.action == "CLICK":
                self.stage = "results"
                self.search_submitted = True
                reward = 0.4
            else:
                reward = -0.1

        elif self.stage == "results":
            clicked_target = False
            if action.action == "CLICK" and action.position is not None:
                for elem in self._results_elements():
                    if elem.text == self.target_result and self._hit(action.position, elem.bbox):
                        clicked_target = True
                        break
            if clicked_target:
                reward = 1.0
                terminated = True
                info["success"] = True
                self.stage = "done"
            else:
                reward = -0.1

        observation = self._build_observation()
        return observation, reward, terminated, info

    def close(self) -> None:
        return None

    def _build_observation(self) -> Observation:
        elements = self._search_elements() if self.stage == "search" else self._results_elements()
        return build_observation(
            task=self.task,
            screenshot_path=f"mock://{self.stage}",
            elements=elements,
            history=self.history,
            metadata={
                "stage": self.stage,
                "task_type": "search_and_open",
                "query": self.query,
                "target_result": self.target_result,
                "screen_size": [1024, 768],
            },
            fields={"query": self.query, "target_result": self.target_result},
        )

    def _search_elements(self) -> list[UIElement]:
        return [
            UIElement("search_box", "Search products", "input", [0.10, 0.10, 0.55, 0.18], ref="search_box"),
            UIElement("search_button", "Search", "button", [0.60, 0.10, 0.75, 0.18], ref="search_button"),
        ]

    def _results_elements(self) -> list[UIElement]:
        return [
            UIElement("result_1", "Lenovo ThinkPad X1 Carbon", "link", [0.10, 0.25, 0.70, 0.33], ref="result_1"),
            UIElement("result_2", "ThinkPad T14 Gen 5", "link", [0.10, 0.38, 0.55, 0.45], ref="result_2"),
            UIElement("result_3", "ThinkBook 14", "link", [0.10, 0.50, 0.40, 0.57], ref="result_3"),
        ]

    @staticmethod
    def _hit(point: list[float], bbox: list[float]) -> bool:
        x, y = point
        x1, y1, x2, y2 = bbox
        return x1 <= x <= x2 and y1 <= y <= y2
