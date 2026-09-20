"""Inspector - record every LLM call and every tool call for the /inspect
slash command.

Records are stored as a flat in-memory list of typed dicts. Three kinds:
  - {"kind": "turn", "user_input": str} - emitted from cli.py when the
    user submits a prompt; renders a "Turn N" separator.
  - {"kind": "llm", "messages": list, "available_tools": list,
    "output_text": str, "output_tool_calls": list} - captured by the
    provider on every LLM call.
  - {"kind": "tool", "name": str, "args": dict, "result": str} -
    captured by ToolRegistry.dispatch on every tool execution.

When /inspect runs, dump() walks the list and prints each record as JSON.
Counters are cumulative across the session. /clear-inspect resets
everything; /clear is independent (does not touch inspector state).
"""

import json

ORANGE = "\033[38;5;208m"
MAGENTA = "\033[38;5;201m"
RESET = "\033[0m"

TURN_COLORS = (ORANGE, MAGENTA)

INPUT_HEADER = "═════════════════════ INPUT ═════════════════════"
OUTPUT_HEADER = "═════════════════════ OUTPUT ════════════════════"
END_HEADER = "═════════════════════════════════════════════════"
BOX_TOP = "╔" + "═" * 47 + "╗"
BOX_BOTTOM = "╚" + "═" * 47 + "╝"

_records: list[dict] = []


def start_turn(user_input: str) -> None:
    """Mark the start of a new user turn - wired to cli.py on each prompt."""
    _records.append({"kind": "turn", "user_input": user_input})


def record(
    messages: list[dict],
    output: str,
    tool_calls: list[dict] | None = None,
    available_tools: list[dict] | None = None,
) -> None:
    """Capture one LLM call's exact input and output."""
    _records.append({
        "kind": "llm",
        "messages": list(messages),
        "available_tools": list(available_tools or []),
        "output_text": output,
        "output_tool_calls": list(tool_calls or []),
    })


def record_tool(name: str, args: dict, result: str) -> None:
    """Capture one tool execution - wired to ToolRegistry.dispatch."""
    _records.append({
        "kind": "tool",
        "name": name,
        "args": dict(args),
        "result": result,
    })


def clear() -> None:
    """Drop all captured records - wired to /clear-inspect."""
    _records.clear()


def dump() -> None:
    """Print every captured record inside one orange box."""
    if not _records:
        print(f"{ORANGE}(nothing recorded yet){RESET}")
        return

    print(ORANGE, end="")
    print()
    print(BOX_TOP)
    print(RESET, end="")

    turn_n = 0
    llm_n = 0
    tool_n = 0
    for rec in _records:
        kind = rec["kind"]
        if kind == "turn":
            if turn_n > 0:
                print(RESET, end="")
            turn_n += 1
            print(TURN_COLORS[(turn_n - 1) % len(TURN_COLORS)], end="")
            print()
            print(f"════════════ Turn {turn_n} ════════════")
            print(f"user input: {rec['user_input']!r}")
        elif kind == "llm":
            llm_n += 1
            print()
            print(f"── LLM Call {llm_n} ──")
            _print_llm_input(rec)
            _print_llm_output(rec)
        elif kind == "tool":
            tool_n += 1
            print()
            print(f"── Tool Call {tool_n} ──")
            _print_tool_input(rec)
            _print_tool_output(rec)

    if turn_n > 0:
        print(RESET, end="")

    print(ORANGE, end="")
    print()
    print(BOX_BOTTOM)
    print(RESET, end="")


def _print_llm_input(rec: dict) -> None:
    print()
    print(INPUT_HEADER)
    print()
    if rec["available_tools"]:
        print(f"tools available ({len(rec['available_tools'])}):")
        print(json.dumps(rec["available_tools"], indent=2, ensure_ascii=False))
        print()
    print("messages:")
    print(json.dumps(rec["messages"], indent=2, ensure_ascii=False))
    print()


def _print_llm_output(rec: dict) -> None:
    print(OUTPUT_HEADER)
    print()
    print("text:")
    print(rec["output_text"] if rec["output_text"] else "(none)")
    print()
    print("tool_calls:")
    if rec["output_tool_calls"]:
        print(json.dumps(rec["output_tool_calls"], indent=2, ensure_ascii=False))
    else:
        print("(none)")
    print()
    print(END_HEADER)


def _print_tool_input(rec: dict) -> None:
    print()
    print(INPUT_HEADER)
    print()
    print(f"tool: {rec['name']}")
    print("arguments:")
    print(json.dumps(rec["args"], indent=2, ensure_ascii=False))
    print()


def _print_tool_output(rec: dict) -> None:
    print(OUTPUT_HEADER)
    print()
    print("result:")
    print(rec["result"] if rec["result"] else "(empty)")
    print()
    print(END_HEADER)
