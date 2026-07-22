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
from gui_agent.policy.miniwob_rule import MiniWoBRulePolicy


def main() -> None:
    try:
        env = MiniWoBEnv(
            env_name="miniwob/click-test-2-v1",
            output_dir=ROOT / "outputs" / "miniwob_click",
            render_mode=None,
            seed=42,
        )
    except ImportError as exc:
        print(exc)
        print("请先安装 `gymnasium` 和 `miniwob`，再运行真实 benchmark 入口。")
        return
    except RuntimeError as exc:
        print(exc)
        print("请检查 Chrome 浏览器和 chromedriver 是否可用，或重新安装 `webdriver-manager`。")
        return

    grounder = KeywordGrounder()
    policy = MiniWoBRulePolicy(grounder=grounder)
    runner = AgentRunner(
        env=env,
        policy=policy,
        output_dir=ROOT / "outputs" / "miniwob_click",
        max_steps=3,
    )
    summary = runner.run()
    print(summary)


if __name__ == "__main__":
    main()
