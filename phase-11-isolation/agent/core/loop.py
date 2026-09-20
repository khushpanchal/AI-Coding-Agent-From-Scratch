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
from agent.memory.compression import auto_compact, micro_compact, should_auto_compact
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
    task_manager=None,
    background_manager=None,
    quiet: bool = False,
) -> None:
    """Run the agent loop until the model stops calling tools.

    Modifies `messages` in-place — appends assistant and tool result messages,
    and may rewrite the list during auto-compaction.

    When `quiet` is True the loop prints nothing — no token stream, no tool
    trace. A backgrounded subagent runs quietly on its own thread so its
    output doesn't interleave with the main loop's; only its summary returns.
    This single flag replaces any need to redirect stdout per thread.
    """
    emit = (lambda *a, **k: None) if quiet else print

    for i in range(max_iterations):
        micro_compact(messages)

        if should_auto_compact(messages):
            emit(f"{DIM}[Compacting context...]{RESET}")
            messages[:] = auto_compact(messages, provider)

        if background_manager:
            for note in background_manager.drain_notifications():
                emit(f"{DIM}[Background task completed]{RESET}")
                messages.append({"role": "user", "content": note})
                messages.append({"role": "assistant", "content": "Noted background task result."})

        if task_manager:
            nag = task_manager.tick()
            if nag:
                messages.append({"role": "user", "content": nag})

        emit(f"{CYAN}", end="")
        stream = provider.chat_stream(
            messages=messages,
            system=system,
            tools=tools.schemas if tools.schemas else None,
        )
        response = print_stream(stream, quiet=quiet)
        emit(RESET, end="")

        _append_assistant_message(messages, response)

        if not response.get("tool_calls"):
            return

        tool_results = []
        for tool_call in response["tool_calls"]:
            name = tool_call["name"]
            args = tool_call["arguments"]

            emit(f"{YELLOW}[tool: {name}]{RESET} ", end="")
            emit(f"{DIM}{_summarize_args(args)}{RESET}")

            result = tools.dispatch(name, args)

            preview = result[:200] + "..." if len(result) > 200 else result
            emit(f"{DIM}{preview}{RESET}\n")

            tool_results.append({
                "tool_call_id": tool_call["id"],
                "tool_name": name,
                "content": result,
            })

        _append_tool_results(messages, tool_results)

    emit(f"{DIM}[Agent reached iteration limit ({max_iterations})]{RESET}")


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
