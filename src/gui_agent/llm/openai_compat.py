from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from gui_agent.llm.base import BaseVisionChatModel, ChatMessage


@dataclass
class OpenAICompatConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0
    timeout_s: int = 120


class OpenAICompatibleVisionModel(BaseVisionChatModel):
    def __init__(self, config: OpenAICompatConfig) -> None:
        self.config = config

    def chat(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
        }
        return self._post_json("/chat/completions", payload)

    def chat_with_image(self, messages: list[ChatMessage], image_path: str) -> str:
        return self.chat_with_images(messages, [image_path])

    def chat_with_images(
        self,
        messages: list[ChatMessage],
        image_paths: list[str],
    ) -> str:
        """Send multiple images in a single message.

        OpenAI vision API supports multiple image_url entries in one content array.
        """
        content: list[dict] = []

        # Collect system text
        system_texts = "\n".join(m.content for m in messages if m.role == "system").strip()
        if system_texts:
            content.append({"type": "text", "text": system_texts})

        # Collect user text
        user_texts = "\n".join(m.content for m in messages if m.role == "user").strip()

        # Add all images
        for img_path in image_paths:
            image_b64, mime = _encode_image_to_base64(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
            })

        # Add user text after images (most models prefer text last)
        if user_texts:
            content.append({"type": "text", "text": user_texts})

        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": self.config.temperature,
        }
        return self._post_json("/chat/completions", payload)

    def _post_json(self, path: str, payload: dict) -> str:
        url = _build_url(self.config.base_url, path)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.config.api_key}")

        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=self.config.timeout_s, context=ctx) as resp:
            text = resp.read().decode("utf-8")
        data = json.loads(text)
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )


def _build_url(base_url: str, path: str) -> str:
    """Build full URL. If base_url already contains a version prefix like /v1 or /api/v3,
    append path directly; otherwise treat base_url as host root and keep path as-is.

    Examples:
        https://api.openai.com/v1        + /chat/completions -> https://api.openai.com/v1/chat/completions
        https://ark.cn-beijing.../api/v3 + /chat/completions -> .../api/v3/chat/completions
    """
    base = base_url.rstrip("/")
    last = base.rsplit("/", 1)[-1]
    if last.startswith("v") and last[1:].isdigit():
        # e.g. /v1, /v3
        return base + path
    if last in ("v1", "v3"):
        return base + path
    # for Ark full path /api/v3
    if base.endswith("/api/v3") or base.endswith("/api/v1"):
        return base + path
    return base + path


def load_openai_compat_from_env(prefix: str = "GUIAGENT_LLM_") -> OpenAICompatConfig | None:
    base_url = os.environ.get(prefix + "BASE_URL", "").strip()
    api_key = os.environ.get(prefix + "API_KEY", "").strip()
    model = os.environ.get(prefix + "MODEL", "").strip()
    temperature = os.environ.get(prefix + "TEMPERATURE", "").strip()

    if not base_url or not api_key or not model:
        return None

    try:
        temp = float(temperature) if temperature else 0.0
    except ValueError:
        temp = 0.0

    return OpenAICompatConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temp,
    )


def _encode_image_to_base64(image_path: str) -> tuple[str, str]:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(image_path)

    raw = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in {".png"}:
        mime = "image/png"
        return base64.b64encode(raw).decode("ascii"), mime
    if suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
        return base64.b64encode(raw).decode("ascii"), mime

    try:
        from PIL import Image
        import io

        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/png"
    except Exception:
        return base64.b64encode(raw).decode("ascii"), "application/octet-stream"
