from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str
    content: str


class BaseChatModel(ABC):
    @abstractmethod
    def chat(self, messages: list[ChatMessage]) -> str:
        raise NotImplementedError


class BaseVisionChatModel(BaseChatModel):
    @abstractmethod
    def chat_with_image(self, messages: list[ChatMessage], image_path: str) -> str:
        raise NotImplementedError

    def chat_with_images(
        self,
        messages: list[ChatMessage],
        image_paths: list[str],
    ) -> str:
        """Send multiple images in a single message.

        Default implementation falls back to the last image only.
        Subclasses (e.g. OpenAI) override this for true multi-image support.
        """
        if not image_paths:
            return self.chat(messages)
        return self.chat_with_image(messages, image_paths[-1])
