"""The Agent Loop — the heart of every AI agent.

The pattern:
    while True:
        response = call_llm(messages, tools)
        if response has tool calls:
            execute each tool
            append results to messages
            continue looping
        else:
            return (the agent is done)

This loop never changes. Future phases add mechanisms *around* it
(compression, planning, background tasks) but the loop itself stays the same.
"""

from agent.core.streaming import print_stream
from agent.providers.base import BaseProvider
from agent.tools.registry import ToolRegistry

CYAN = "\033[36m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

MAX_ITERATIONS = 50


def agent_loop(
    provider: BaseProvider,
    messages: list[dict],
    tools: ToolRegistry,
    system: str = "",
    max_iterations: int = MAX_ITERATIONS,
) -> None:
    """Run the agent loop until the model stops calling tools.

    Modifies `messages` in-place — appends assistant and tool result messages.
    """
    for i in range(max_iterations):
        print(f"{CYAN}", end="")
        stream = provider.chat_stream(
            messages=messages,
            system=system,
            tools=tools.schemas if tools.schemas else None,
        )
        response = print_stream(stream)
        print(RESET, end="")

        _append_assistant_message(messages, response)

        if not response.get("tool_calls"):
            return

        tool_results = []
        for tool_call in response["tool_calls"]:
            name = tool_call["name"]
            args = tool_call["arguments"]

            print(f"{YELLOW}[tool: {name}]{RESET} ", end="")
            print(f"{DIM}{_summarize_args(args)}{RESET}")

            result = tools.dispatch(name, args)

            preview = result[:200] + "..." if len(result) > 200 else result
            print(f"{DIM}{preview}{RESET}\n")

            tool_results.append({
                "tool_call_id": tool_call["id"],
                "tool_name": name,
                "content": result,
            })

        _append_tool_results(messages, tool_results)

    print(f"{DIM}[Agent reached iteration limit ({max_iterations})]{RESET}")


def _append_assistant_message(messages: list[dict], response: dict):
    msg = {"role": "assistant", "content": response.get("content", "") or None}
    if response.get("tool_calls"):
        msg["tool_calls"] = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            }
            for tc in response["tool_calls"]
        ]
    messages.append(msg)


def _append_tool_results(messages: list[dict], results: list[dict]):
    for r in results:
        messages.append({
            "role": "tool",
            "tool_call_id": r["tool_call_id"],
            "content": r["content"],
        })


def _summarize_args(args: dict) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
