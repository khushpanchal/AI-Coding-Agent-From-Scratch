"""Abstract base class for all LLM providers.

Every provider must translate between a unified message format and its
native SDK.  The unified format uses standard chat dicts:

    {"role": "user", "content": "Hello"}
    {"role": "assistant", "content": "Hi there!"}

Providers convert these internally before calling their SDK.
"""

from abc import ABC, abstractmethod
from typing import Generator


class BaseProvider(ABC):
    """Interface that every provider implements."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        """Send messages and return a complete response.

        Returns a dict with:
            role: "assistant"
            content: str | list   — text or list of content blocks
            tool_calls: list      — tool call requests (if any)
            stop_reason: str      — "end_turn", "tool_use", etc.
        """

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> Generator[dict, None, None]:
        """Stream response tokens.

        Yields dicts with:
            type: "text" | "tool_call" | "done"
            content: str           — for text chunks
            tool_call: dict        — for tool_call events
            stop_reason: str       — for done events
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
