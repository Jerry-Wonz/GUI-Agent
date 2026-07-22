from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.env.miniwob_env import MiniWoBEnv
from gui_agent.executor.loop import AgentRunner
from gui_agent.grounding.keyword_grounder import KeywordGrounder
from gui_agent.llm.factory import create_default_vlm
from gui_agent.policy.llm_grounded import LLMGroundedPolicy


def main() -> None:
    model = create_default_vlm()
    if model is None:
        print("未检测到 LLM/VLM 配置。请设置 GUIAGENT_LLM_BASE_URL / GUIAGENT_LLM_API_KEY / GUIAGENT_LLM_MODEL。")
        return

    env = MiniWoBEnv(
        env_name="miniwob/click-test-2-v1",
        output_dir=ROOT / "outputs" / "miniwob_click_vlm",
        render_mode=None,
        seed=42,
        episode_timeout_ms=30000,
    )
    grounder = KeywordGrounder()
    policy = LLMGroundedPolicy(grounder=grounder, model=model, use_vision=True)
    runner = AgentRunner(
        env=env,
        policy=policy,
        output_dir=ROOT / "outputs" / "miniwob_click_vlm",
        max_steps=3,
    )
    summary = runner.run()
    print(summary)


if __name__ == "__main__":
    main()
