"""Memory module for tracking agent progress and patterns across steps.

Provides a lightweight, in-memory store of step-level outcomes that can be
injected into the VLM prompt as context. This gives the model awareness of
what worked, what failed, and what has already been attempted.
"""

from __future__ import annotations

from typing import Any


class TaskMemory:
    """Tracks step-level outcomes and extracts patterns for prompt injection.

    This is an in-memory, step-local store. It does not persist across runs.
    """

    def __init__(self, max_context_steps: int = 5) -> None:
        self._steps: list[dict[str, Any]] = []
        self._max_context_steps = max_context_steps

    def record(
        self,
        step_id: int,
        action_type: str,
        target_text: str | None,
        position: list[float] | None,
        grounding_score: float,
        grounding_source: str,
        reward: float,
        error: str | None,
    ) -> None:
        """Record a completed step's outcome."""
        self._steps.append({
            "step": step_id,
            "action": action_type,
            "target": target_text or "",
            "position": position,
            "grounding_score": grounding_score,
            "grounding_source": grounding_source,
            "reward": reward,
            "error": error,
        })
        # Keep only recent steps
        if len(self._steps) > self._max_context_steps:
            self._steps = self._steps[-self._max_context_steps :]

    def get_progress_summary(self) -> str:
        """Generate a brief text summary of recent progress for prompt injection."""
        if not self._steps:
            return "No prior steps."
        lines = ["Recent progress:"]
        for s in self._steps[-3:]:
            status = "FAILED" if s["error"] else "OK"
            lines.append(
                f"  Step {s['step']}: {s['action']} "
                f"target='{s['target'][:30]}' "
                f"score={s['grounding_score']:.2f} "
                f"reward={s['reward']} "
                f"[{status}]"
            )
        return "\n".join(lines)

    def get_grounding_patterns(self) -> dict[str, float]:
        """Return average grounding scores per source (which methods work best)."""
        patterns: dict[str, list[float]] = {}
        for s in self._steps:
            src = s.get("grounding_source", "unknown")
            if src not in patterns:
                patterns[src] = []
            patterns[src].append(s["grounding_score"])
        return {
            src: round(sum(scores) / len(scores), 4)
            for src, scores in patterns.items()
        }

    def recent_actions(self, count: int = 3) -> list[dict[str, Any]]:
        """Return the most recent step records (for logging/debugging)."""
        return self._steps[-count:]
