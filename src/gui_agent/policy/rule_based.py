from __future__ import annotations

from gui_agent.grounding.base import BaseGrounder
from gui_agent.policy.base import BasePolicy
from gui_agent.schemas import Action, Observation


class RuleBasedPolicy(BasePolicy):
    """A simple baseline to complete search-and-open style tasks."""

    def __init__(self, grounder: BaseGrounder) -> None:
        self.grounder = grounder
        self.last_grounding = None

    def act(self, observation: Observation) -> Action:
        stage = observation.metadata.get("stage")
        task_type = observation.metadata.get("task_type")

        if task_type != "search_and_open":
            return Action(action="STOP")

        query = observation.metadata.get("query", "")
        target = observation.metadata.get("target_result", "")

        if stage == "search":
            typed = any(item.get("action") == "TYPE" for item in observation.history)
            if not typed:
                grounding = self.grounder.predict(
                    screenshot_path=observation.screenshot_path,
                    query="search",
                    elements=observation.elements,
                    dom_text=observation.dom_text,
                )
                self.last_grounding = grounding.to_dict()
                return Action(
                    action="TYPE",
                    value=query,
                    position=grounding.point,
                    metadata={"ref": grounding.matched_ref},
                )

            grounding = self.grounder.predict(
                screenshot_path=observation.screenshot_path,
                query="search",
                elements=observation.elements,
                dom_text=observation.dom_text,
            )
            self.last_grounding = grounding.to_dict()
            return Action(
                action="CLICK",
                position=grounding.point,
                metadata={"ref": grounding.matched_ref},
            )

        if stage == "results":
            grounding = self.grounder.predict(
                screenshot_path=observation.screenshot_path,
                query=target,
                elements=observation.elements,
                dom_text=observation.dom_text,
            )
            self.last_grounding = grounding.to_dict()
            if grounding.point is not None:
                return Action(
                    action="CLICK",
                    position=grounding.point,
                    metadata={"ref": grounding.matched_ref},
                )
            return Action(action="SCROLL", value="down")

        return Action(action="STOP")
