from __future__ import annotations

from abc import ABC, abstractmethod

from gui_agent.schemas import Action, Observation


class BasePolicy(ABC):
    @abstractmethod
    def act(self, observation: Observation) -> Action:
        raise NotImplementedError
