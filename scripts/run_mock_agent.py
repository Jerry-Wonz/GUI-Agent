from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.env.mock_web import MockWebEnv
from gui_agent.executor.loop import AgentRunner
from gui_agent.grounding.keyword_grounder import KeywordGrounder
from gui_agent.policy.rule_based import RuleBasedPolicy


def main() -> None:
    env = MockWebEnv()
    grounder = KeywordGrounder()
    policy = RuleBasedPolicy(grounder=grounder)
    output_dir = ROOT / "outputs" / "mock_run"

    runner = AgentRunner(
        env=env,
        policy=policy,
        output_dir=output_dir,
        max_steps=5,
    )
    summary = runner.run()
    print(summary)


if __name__ == "__main__":
    main()
