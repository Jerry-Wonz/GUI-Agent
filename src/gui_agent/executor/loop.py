from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from gui_agent.env.base import BaseWebEnv
from gui_agent.evaluation.metrics import summarize_records
from gui_agent.memory.task_memory import TaskMemory
from gui_agent.policy.base import BasePolicy
from gui_agent.schemas import StepRecord
from gui_agent.utils.io import append_jsonl, ensure_dir, write_json


class AgentRunner:
    def __init__(
        self,
        env: BaseWebEnv,
        policy: BasePolicy,
        output_dir: str | Path,
        max_steps: int = 5,
        enable_memory: bool = True,
    ) -> None:
        self.env = env
        self.policy = policy
        self.output_dir = ensure_dir(output_dir)
        self.max_steps = max_steps
        self.enable_memory = enable_memory
        self.memory = TaskMemory() if enable_memory else None

    def run(self) -> dict:
        records_path = self.output_dir / "steps.jsonl"
        summary_path = self.output_dir / "summary.json"

        observation = self.env.reset()
        records: list[StepRecord] = []
        # 历史记忆：记录每一步的动作和结果
        history: list[dict[str, Any]] = []

        for step_id in range(self.max_steps):
            # 注入记忆上下文
            if self.memory:
                progress = self.memory.get_progress_summary()
                observation.metadata["progress_summary"] = progress
                patterns = self.memory.get_grounding_patterns()
                if patterns:
                    observation.metadata["grounding_patterns"] = patterns

            # 将历史注入 observation
            observation.history = list(history)

            think_started = time.perf_counter()
            action = self.policy.act(observation)
            think_time_s = max(0.0, time.perf_counter() - think_started)
            action.metadata["think_time_s"] = round(think_time_s, 4)
            compensate = getattr(self.env, "compensate_think_time", None)
            if callable(compensate):
                compensate(think_time_s)
            next_observation, reward, terminated, info = self.env.step(action)
            grounding = getattr(self.policy, "last_grounding", None)

            record = StepRecord(
                step_id=step_id,
                task=observation.task,
                observation=observation.to_dict(),
                grounding=grounding,
                action=action.to_dict(),
                reward=reward,
                terminated=terminated,
                info=info,
            )
            records.append(record)
            append_jsonl(records_path, record.to_dict())

            # 记录到记忆模块
            if self.memory:
                error_str = info.get("action_error", "")
                grounding = getattr(self.policy, "last_grounding", None) or {}
                self.memory.record(
                    step_id=step_id,
                    action_type=action.action,
                    target_text=action.metadata.get("target_text"),
                    position=action.position,
                    grounding_score=grounding.get("score", 0.0),
                    grounding_source=grounding.get("source", "unknown"),
                    reward=reward,
                    error=error_str if error_str else None,
                )

            # 构建历史条目
            error_str = info.get("action_error", "")
            history_entry: dict[str, Any] = {
                "step": step_id,
                "action": action.action,
                "value": action.value,
                "url": observation.metadata.get("current_url", ""),
                "screenshot_path": observation.screenshot_path,
            }
            if error_str:
                history_entry["error"] = _summarize_error(error_str)
            if action.action == "STOP":
                pass  # 停止动作也记录
            history.append(history_entry)
            # 只保留最近 N 条历史
            max_hist = getattr(self.policy, "max_history", 5)
            history = history[-max_hist:]

            observation = next_observation
            if terminated or action.action == "STOP":
                break

        summary = summarize_records(records)

        # Enhanced summary (Phase 5: ShowUI-inspired evaluation)
        from gui_agent.evaluation.metrics import (
            grounding_accuracy_per_action,
            error_classification,
            vlm_response_quality,
        )

        summary["grounding_accuracy"] = grounding_accuracy_per_action(records)
        summary["error_types"] = error_classification(records)
        summary["vlm_quality"] = vlm_response_quality(records)

        write_json(summary_path, summary)
        self.env.close()
        return summary


def _summarize_error(error: str) -> str:
    """截取关键的错误信息摘要。"""
    if "invalid element state" in error:
        return "invalid_element_state (clicked non-input element)"
    if "no such element" in error:
        return "element_not_found"
    if "timeout" in error.lower():
        return "timeout"
    # 取第一行 80 字符
    first_line = error.split("\n")[0]
    return first_line[:80]
