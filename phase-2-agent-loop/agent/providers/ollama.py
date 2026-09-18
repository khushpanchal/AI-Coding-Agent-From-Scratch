"""Ollama provider — local models via the official Ollama Python SDK."""

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

    def chat(self, messages, system="", tools=None, max_tokens=4096) -> dict:
        msgs = self._inject_system(messages, system)
        kwargs = {"model": self._model, "messages": msgs}
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.chat(**kwargs)
        parsed = self._parse_response(response)
        inspector.record(
            msgs,
            parsed.get("content", "") or "",
            parsed.get("tool_calls") or [],
            available_tools=kwargs.get("tools", []),
        )
        return parsed

    def chat_stream(self, messages, system="", tools=None, max_tokens=4096) -> Generator[dict, None, None]:
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
                        "id": tc.function.name,
                        "name": tc.function.name,
                        "arguments": dict(tc.function.arguments),
                    }
                    parsed_tools.append(parsed)
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

    def _parse_response(self, response) -> dict:
        tool_calls = []
        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                tool_calls.append({
                    "id": tc.function.name,
                    "name": tc.function.name,
                    "arguments": dict(tc.function.arguments),
                })

        stop = "tool_use" if tool_calls else "end_turn"

        return {
            "role": "assistant",
            "content": response.message.content or "",
            "tool_calls": tool_calls,
            "stop_reason": stop,
        }
