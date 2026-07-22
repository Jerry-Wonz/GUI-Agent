from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.env.selenium_web_env import SeleniumWebEnv
from gui_agent.executor.loop import AgentRunner
from gui_agent.grounding.keyword_grounder import KeywordGrounder
from gui_agent.llm.factory import create_default_vlm
from gui_agent.policy.llm_grounded import LLMGroundedPolicy


def main() -> None:
    model = create_default_vlm()
    if model is None:
        print("未检测到 LLM/VLM 配置。请设置 GUIAGENT_LLM_BASE_URL / GUIAGENT_LLM_API_KEY / GUIAGENT_LLM_MODEL。")
        return

    env = SeleniumWebEnv(
        start_url="https://en.wikipedia.org/wiki/Main_Page",
        task="Search for 'Artificial intelligence' in the search box on this page.",
        output_dir=ROOT / "outputs" / "real_web_vlm",
        window_size=(1024, 768),
        success_url_substring="Artificial_intelligence",
        max_steps=4,
        headless=True,
        auto_submit_on_type=True,
    )
    grounder = KeywordGrounder()
    policy = LLMGroundedPolicy(grounder=grounder, model=model, use_vision=True)
    runner = AgentRunner(
        env=env,
        policy=policy,
        output_dir=ROOT / "outputs" / "real_web_vlm",
        max_steps=4,
    )
    summary = runner.run()
    print(summary)


if __name__ == "__main__":
    main()
