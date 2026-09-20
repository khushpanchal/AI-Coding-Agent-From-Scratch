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
    """Interface that every provider implements.

    This project only ever *streams*, so the interface is a single
    streaming method - no blocking `chat()`. Streaming is what lets a tool
    start the instant its call is parsed, which is the whole point.
    """

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        """Stream response tokens.

        Yields dicts with:
            type: "text" | "tool_call" | "done"
            content: str           - for text chunks
            tool_call: dict        - for tool_call events
            stop_reason: str       - for done events

        The "tool_call" event is the one this whole project is about: it is
        yielded the *instant* a tool call is parsed out of the stream, so a
        StreamingToolExecutor can start running that tool before the model
        has finished generating the rest of its response.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
