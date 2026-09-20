"""The Agent Loop - the heart of every AI agent.

The pattern:

    while True:
        response = call_llm(messages, tools)
        if response has tool calls:
            execute each tool
            append results to messages
            continue looping
        else:
            return (the agent is done)

The ONLY thing this project changes is the "execute each tool" step. That
job is delegated to the StreamingToolExecutor (agent/core/executor.py): it
starts each tool the instant its call appears in the stream, while the model
is still generating. Every turn it also reports what the classic
non-streaming approach would have cost on the same response, so the saving is
visible without a second run.

Same loop, same tools, same model - just tools that start earlier.
"""

from agent.core.executor import ExecutionResult, StreamingToolExecutor
from agent.core.streaming import write_text
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

    Modifies `messages` in-place. Tools execute via the StreamingToolExecutor.
    """
    executor = StreamingToolExecutor()

    for _ in range(max_iterations):
        print(CYAN, end="")
        stream = provider.chat_stream(
            messages=messages,
            system=system,
            tools=tools.schemas if tools.schemas else None,
        )
        result = executor.run(stream, tools, on_text=write_text)
        print(RESET, end="")

        _append_assistant_message(messages, result.response)

        if not result.response.get("tool_calls"):
            return

        _print_tool_report(result)
        _append_tool_results(messages, result.tool_results)
        print(result.format_summary())
        print()

    print(f"{DIM}[Agent reached iteration limit ({max_iterations})]{RESET}")


def _print_tool_report(result: ExecutionResult) -> None:
    """Show each tool with its timeline so the overlap is visible.

    The 'fired @' stamps land *during* the stream (each tool starts the
    instant its call arrives), and the run windows overlap - that early start
    plus the overlap with token generation is what the summary measures
    against the non-streaming counterfactual.
    """
    print()
    for r in result.runs:
        print(f"{YELLOW}[tool: {r.name}]{RESET} {DIM}{_summarize_args(r.args)}{RESET}")
        print(
            f"   {DIM}⤷ fired @ {r.submitted_at:5.2f}s · "
            f"ran {r.duration:4.2f}s · done @ {r.finished_at:5.2f}s{RESET}"
        )
        preview = r.result[:160].replace("\n", " ⏎ ")
        if len(r.result) > 160:
            preview += "..."
        print(f"   {DIM}{preview}{RESET}")


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
