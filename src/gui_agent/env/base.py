from __future__ import annotations

from abc import ABC, abstractmethod

from gui_agent.schemas import Action, Observation


class BaseWebEnv(ABC):
    @abstractmethod
    def reset(self) -> Observation:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: Action) -> tuple[Observation, float, bool, dict]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError
