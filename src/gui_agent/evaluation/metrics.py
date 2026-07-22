from __future__ import annotations

from gui_agent.schemas import StepRecord


def summarize_records(records: list[StepRecord]) -> dict:
    total_steps = len(records)
    total_reward = round(sum(record.reward for record in records), 4)
    success = any(
        bool(record.info.get("success"))
        or (bool(record.terminated) and float(record.reward) > 0)
        for record in records
    )

    return {
        "total_steps": total_steps,
        "total_reward": total_reward,
        "success": success,
    }


def grounding_accuracy(results: list[bool]) -> float:
    if not results:
        return 0.0
    return round(sum(1 for item in results if item) / len(results), 4)


# ── Enhanced Evaluation: Phase 5 (ShowUI-inspired) ──


def grounding_accuracy_per_action(records: list[StepRecord]) -> dict[str, dict]:
    """Grounding hit rate broken down by action type.

    Returns a dict like:
        {"CLICK": {"total": 3, "hit": 2, "miss": 1, "accuracy": 0.6667, "sources": {...}}}
    """
    action_stats: dict[str, dict] = {}
    for record in records:
        action_type = record.action.get("action", "UNKNOWN")
        grounding = record.grounding or {}
        score = grounding.get("score", 0.0)
        point = grounding.get("point")
        source = grounding.get("source", "unknown")

        if action_type not in action_stats:
            action_stats[action_type] = {"total": 0, "hit": 0, "miss": 0, "sources": {}}

        action_stats[action_type]["total"] += 1
        if point is not None and score > 0:
            action_stats[action_type]["hit"] += 1
        else:
            action_stats[action_type]["miss"] += 1

        if source not in action_stats[action_type]["sources"]:
            action_stats[action_type]["sources"][source] = 0
        action_stats[action_type]["sources"][source] += 1

    for action_type, stats in action_stats.items():
        stats["accuracy"] = (
            round(stats["hit"] / stats["total"], 4) if stats["total"] > 0 else 0.0
        )

    return action_stats


def error_classification(records: list[StepRecord]) -> dict[str, int]:
    """Classify errors into perception/grounding/decision/execution."""
    counts: dict[str, int] = {
        "perception": 0,
        "grounding": 0,
        "decision": 0,
        "execution": 0,
        "none": 0,
    }
    for record in records:
        error_type = classify_single_error(record)
        counts[error_type] = counts.get(error_type, 0) + 1
    return counts


def classify_single_error(record: StepRecord) -> str:
    """Classify a single step error into one of five categories."""
    grounding = record.grounding or {}
    action = record.action or {}
    info = record.info or {}

    # Execution error: action was valid but environment failed
    if info.get("action_error"):
        return "execution"

    # Grounding error: VLM identified element but position couldn't be resolved
    action_type = action.get("action", "").upper()
    if action_type in ("CLICK", "TYPE") and grounding.get("point") is None and grounding.get("query"):
        return "grounding"

    # Perception error: VLM couldn't generate a valid target
    if not grounding.get("query") and action_type in ("CLICK", "TYPE"):
        if record.reward == 0:
            return "perception"

    # Decision error: action happened but was wrong
    if record.reward <= 0 and not info.get("action_error"):
        return "decision"

    return "none"


def vlm_response_quality(records: list[StepRecord]) -> dict:
    """Track VLM response parse rate and quality."""
    total = len(records)
    json_success = sum(1 for r in records if _vlm_json_was_valid(r))
    return {
        "total_calls": total,
        "valid_json": json_success,
        "valid_json_rate": round(json_success / total, 4) if total > 0 else 0.0,
    }


def _vlm_json_was_valid(record: StepRecord) -> bool:
    """Heuristic: check if VLM output a recognizable action."""
    return bool(record.action.get("action")) and record.action["action"] != "STOP"
