from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 自动加载项目根目录下的 .env 文件（如果存在）
_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=_env_path, override=False)

from gui_agent.llm.base import BaseChatModel, BaseVisionChatModel
from gui_agent.llm.openai_compat import OpenAICompatibleVisionModel, load_openai_compat_from_env
from gui_agent.llm.zhipu_paas_v4 import ZhipuPaaSV4VisionModel, load_zhipu_paas_v4_from_env


def create_default_vlm() -> BaseVisionChatModel | None:
    provider = os.environ.get("GUIAGENT_LLM_PROVIDER", "").strip().lower()
    base_url = os.environ.get("GUIAGENT_LLM_BASE_URL", "").strip()

    if provider == "zhipu" or (not provider and "/api/paas/v4" in base_url):
        cfg = load_zhipu_paas_v4_from_env()
        if not cfg:
            return None
        return ZhipuPaaSV4VisionModel(cfg)

    cfg = load_openai_compat_from_env()
    if not cfg:
        return None
    return OpenAICompatibleVisionModel(cfg)


def create_default_llm() -> BaseChatModel | None:
    return create_default_vlm()
