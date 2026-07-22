from __future__ import annotations

from gui_agent.grounding.base import BaseGrounder
from gui_agent.policy.base import BasePolicy
from gui_agent.schemas import Action, Observation


class MiniWoBRulePolicy(BasePolicy):
    """
    A lightweight policy for simple MiniWoB tasks such as click-test variants.
    """

    def __init__(self, grounder: BaseGrounder) -> None:
        self.grounder = grounder
        self.last_grounding = None

    def act(self, observation: Observation) -> Action:
        self.last_grounding = None

        target_text = self._extract_target_text(observation)
        if not target_text:
            return Action(action="STOP", metadata={"reason": "no_target"})

        grounding = self.grounder.predict(
            screenshot_path=observation.screenshot_path,
            query=target_text,
            elements=observation.elements,
            dom_text=observation.dom_text,
        )
        self.last_grounding = grounding.to_dict()

        if grounding.point is None:
            return Action(action="STOP", metadata={"reason": "grounding_failed"})

        return Action(
            action="CLICK",
            position=grounding.point,
            metadata={"ref": grounding.matched_ref, "target_text": target_text},
        )

    @staticmethod
    def _extract_target_text(observation: Observation) -> str | None:
        fields = observation.fields or {}
        for key in ("target", "button", "item", "text"):
            value = fields.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        task = observation.task.strip()
        if "Click button " in task:
            return task.split("Click button ", 1)[1].rstrip(". ")
        if "Click " in task:
            return task.split("Click ", 1)[1].rstrip(". ")
        return None
