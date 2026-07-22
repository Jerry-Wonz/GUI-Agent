"""Error classification for GUI agent steps.

Provides helper functions to classify step-level errors into one of five
categories: perception, grounding, decision, execution, none.
"""

from gui_agent.evaluation.metrics import classify_single_error, error_classification

__all__ = ["classify_single_error", "error_classification"]
