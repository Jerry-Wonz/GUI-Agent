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

    # 使用百度作为起点，因为在中国更稳定
    env = SeleniumWebEnv(
        start_url="https://www.baidu.com",
        task="在搜索框中搜索“百度地图”，点击结果中的百度地图链接，然后在百度地图搜索框中搜索“厦门市”。",
        output_dir=ROOT / "outputs" / "baidu_maps_xiamen",
        window_size=(1280, 800),
        success_url_substring="map.baidu.com",
        success_text="厦门市",
        max_steps=12,
        headless=False,
        auto_submit_on_type=True,
        browser="chrome",
    )
    grounder = KeywordGrounder()
    policy = LLMGroundedPolicy(grounder=grounder, model=model, use_vision=True)
    runner = AgentRunner(
        env=env,
        policy=policy,
        output_dir=ROOT / "outputs" / "baidu_maps_xiamen",
        max_steps=12,
    )
    summary = runner.run()
    print("\n=== 任务结果 ===")
    print(summary)


if __name__ == "__main__":
    main()
