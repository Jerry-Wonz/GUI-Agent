from __future__ import annotations

from gui_agent.env.base import BaseWebEnv
from gui_agent.schemas import Action, Observation


class BrowserGymEnv(BaseWebEnv):
    """Placeholder adapter for future BrowserGym integration."""

    def __init__(self, env_name: str) -> None:
        self.env_name = env_name

    def reset(self) -> Observation:
        raise NotImplementedError(
            "BrowserGym adapter is reserved for future integration. "
            "See docs/references.md and docs/tasks.md for the next implementation step."
        )

    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        raise NotImplementedError(
            "BrowserGym adapter is reserved for future integration."
        )

    def close(self) -> None:
        return None
