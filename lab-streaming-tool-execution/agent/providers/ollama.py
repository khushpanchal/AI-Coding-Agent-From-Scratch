"""Ollama provider - local models via the official Ollama Python SDK.

Every tool call gets a **unique id** (`<name>-<index>`). A naive approach
uses the tool's name as its id, which collides when the model asks for the
same tool twice in one response - exactly the parallel-tool-call case that
makes streaming execution shine. Unique ids let us match each result back to
the right call.
"""

from typing import Generator

from agent.core import inspector
from agent.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    def __init__(self, model: str, host: str = "http://localhost:11434"):
        from ollama import Client

        self._client = Client(host=host)
        self._model = model

    @property
    def name(self) -> str:
        return f"Ollama ({self._model})"

    def chat_stream(self, messages, system="", tools=None) -> Generator[dict, None, None]:
        msgs = self._inject_system(messages, system)
        kwargs = {"model": self._model, "messages": msgs, "stream": True}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        text_content = ""
        parsed_tools = []

        for chunk in self._client.chat(**kwargs):
            if chunk.message.content:
                text_content += chunk.message.content
                yield {"type": "text", "content": chunk.message.content}

            if chunk.message.tool_calls:
                for tc in chunk.message.tool_calls:
                    parsed = {
                        "id": f"{tc.function.name}-{len(parsed_tools)}",
                        "name": tc.function.name,
                        "arguments": dict(tc.function.arguments),
                    }
                    parsed_tools.append(parsed)
                    # The key event: emit the tool call the moment it is
                    # parsed, NOT at the end. A streaming executor pounces
                    # on this immediately.
                    yield {"type": "tool_call", "tool_call": parsed}

            if chunk.done:
                stop = "tool_use" if parsed_tools else "end_turn"
                yield {
                    "type": "done",
                    "stop_reason": stop,
                    "response": {
                        "role": "assistant",
                        "content": text_content,
                        "tool_calls": parsed_tools,
                        "stop_reason": stop,
                    },
                }

        inspector.record(msgs, text_content, parsed_tools, available_tools=kwargs.get("tools", []))

    def _inject_system(self, messages: list[dict], system: str) -> list[dict]:
        if not system:
            return messages
        return [{"role": "system", "content": system}] + messages

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return result
