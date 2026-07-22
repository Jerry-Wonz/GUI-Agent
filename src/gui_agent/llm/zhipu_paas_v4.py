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
class ZhipuPaaSV4Config:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0
    timeout_s: int = 120


class ZhipuPaaSV4VisionModel(BaseVisionChatModel):
    def __init__(self, config: ZhipuPaaSV4Config) -> None:
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
        """Send multiple images (Zhipu API supports multi-image via content array)."""
        system_texts = "\n".join(m.content for m in messages if m.role == "system").strip()
        user_texts = "\n".join(m.content for m in messages if m.role == "user").strip()

        content: list[dict] = []
        if system_texts:
            content.append({"type": "text", "text": system_texts})
        if user_texts:
            content.append({"type": "text", "text": user_texts})

        for img_path in image_paths:
            image_b64, mime = _encode_image_to_base64(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
            })

        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": self.config.temperature,
        }
        return self._post_json("/chat/completions", payload)

    def _post_json(self, path: str, payload: dict) -> str:
        url = self.config.base_url.rstrip("/") + path
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.config.api_key}")

        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=self.config.timeout_s, context=ctx) as resp:
            text = resp.read().decode("utf-8")
        data = json.loads(text)
        return _extract_content(data)


def load_zhipu_paas_v4_from_env(prefix: str = "GUIAGENT_LLM_") -> ZhipuPaaSV4Config | None:
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

    return ZhipuPaaSV4Config(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temp,
    )


def _extract_content(data: dict) -> str:
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", None)
    )
    if isinstance(content, str):
        return content

    content = (
        data.get("data", {})
        .get("choices", [{}])[0]
        .get("message", {})
        .get("content", None)
    )
    if isinstance(content, str):
        return content

    return ""


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
