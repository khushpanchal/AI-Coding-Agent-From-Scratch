"""CLI entry point - interactive REPL.

A small, local AI agent (CLI + Ollama + agent loop) built around one idea:
**Streaming Tool Execution**. The agent starts each tool the instant its
call appears in the model's stream, while the model is still generating.

    python -m agent.cli

Every tool-using turn prints a timing block that compares, on the SAME
response, what streaming actually cost vs. what the classic non-streaming
approach (wait for the full response, then run the tools) would have cost -
so you see the saving directly, with no second run and no model-variance
noise.
"""

import argparse

from agent.core import inspector
from agent.core.config import get_config
from agent.core.loop import agent_loop
from agent.providers.registry import get_provider
from agent.tools.registry import ToolRegistry
from agent.tools.simulated import LATENCY, register_all

GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


SYSTEM_PROMPT = """\
You are a helpful AI agent with these tools: read_file, run_tests,
web_search, lint_code, db_query. When the user asks you to do something,
call the tools needed to do it. Prefer to request ALL the tools you need in
one response (multiple tool calls at once) rather than one per turn - so the
first call streams in early and its tool starts while the rest generate.
After the tools return, give a short final answer. Act directly; do the
work, don't just describe it.\
"""


def print_banner(provider_name: str):
    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║         Streaming Tool Execution         ║
║   Tools start the moment they stream in  ║
╚══════════════════════════════════════════╝{RESET}
{DIM}Provider: {provider_name}
Each turn compares streaming vs non-streaming on the same response.
Type /help for commands, /quit to exit.{RESET}
""")


def setup_tools() -> ToolRegistry:
    """Register all simulated tools (hardcoded tasks with fixed latency)."""
    registry = ToolRegistry()
    register_all(registry)
    return registry


def print_help():
    tool_lats = ", ".join(f"{n} {s:.1f}s" for n, s in LATENCY.items())
    print(f"""{DIM}Commands:
  /model         - Show current provider and model
  /inspect       - Show every LLM call's input and output
  /clear-inspect - Clear inspector records (independent of /clear)
  /clear         - Clear conversation history
  /help          - Show this help
  /quit          - Exit the agent

Tools always start the instant their call streams in. Each turn's timing
block compares that against the non-streaming approach on the same response.

Try asking:
  "read src/app.py, run the tests, and search docs for streaming tools"
  → fires several tools at once; watch the timing block.

Simulated tool latencies: {tool_lats}{RESET}""")


def main():
    parser = argparse.ArgumentParser(prog="agent", description="Streaming Tool Execution demo agent.")
    parser.parse_args()

    config = get_config()

    provider = get_provider(config)
    tools = setup_tools()
    print_banner(provider.name)

    messages: list[dict] = []

    while True:
        try:
            user_input = input(f"{GREEN}> {RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}Goodbye!{RESET}")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print(f"{DIM}Goodbye!{RESET}")
            break
        elif user_input == "/help":
            print_help()
            continue
        elif user_input == "/clear":
            messages.clear()
            print(f"{DIM}Conversation cleared.{RESET}")
            continue
        elif user_input == "/model":
            print(f"{DIM}{provider.name}{RESET}")
            continue
        elif user_input == "/inspect":
            inspector.dump()
            continue
        elif user_input == "/clear-inspect":
            inspector.clear()
            print(f"{DIM}Inspector records cleared.{RESET}")
            continue

        inspector.start_turn(user_input)
        messages.append({"role": "user", "content": user_input})

        try:
            agent_loop(
                provider=provider,
                messages=messages,
                tools=tools,
                system=SYSTEM_PROMPT,
            )
        except Exception as e:
            print(f"{RESET}\033[31mError: {e}\033[0m")
            if messages and messages[-1].get("role") == "user":
                messages.pop()


if __name__ == "__main__":
    main()
