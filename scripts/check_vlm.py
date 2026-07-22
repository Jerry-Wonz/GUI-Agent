"""快速验证 VLM 配置是否可用。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gui_agent.llm.factory import create_default_vlm
from gui_agent.llm.base import ChatMessage


def main() -> None:
    model = create_default_vlm()
    if model is None:
        print("[FAIL] 未检测到 LLM/VLM 配置。请设置 GUIAGENT_LLM_BASE_URL / API_KEY / MODEL。")
        sys.exit(1)

    print(f"[OK] 模型已加载: {model.__class__.__name__}")
    print(f"     base_url: {model.config.base_url}")
    print(f"     model:    {model.config.model}")
    print()
    print("[..] 发送简单文本测试请求...")

    try:
        resp = model.chat([
            ChatMessage(role="system", content="你是一个助手，请用一句话回答。"),
            ChatMessage(role="user", content="用中文说一句：配置成功！"),
        ])
        print("[OK] 文本请求成功！")
        print(f"     回复: {resp}")
    except Exception as exc:
        print(f"[FAIL] 文本请求失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
