"""CLI entry point — interactive REPL."""

import sys

from agent.core import inspector
from agent.core.config import get_config
from agent.core.loop import agent_loop
from agent.providers.registry import get_provider
from agent.tools.bash import BASH_SCHEMA, handle_bash
from agent.tools.registry import ToolRegistry

CYAN = "\033[36m"
GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


SYSTEM_PROMPT = """\
You are a helpful AI coding agent. Use the bash tool to run shell commands
when the user asks you to do something. Act directly — do the work, don't
just plan it.\
"""


def print_banner(provider_name: str):
    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║            AI Coding Agent               ║
║           Agent Loop + Bash              ║
╚══════════════════════════════════════════╝{RESET}
{DIM}Provider: {provider_name}
Type /quit to exit, /help for commands.{RESET}
""")


def setup_tools() -> ToolRegistry:
    """Register all available tools."""
    registry = ToolRegistry()
    registry.register(BASH_SCHEMA, handle_bash)
    return registry


def main():
    try:
        config = get_config()
    except ValueError as e:
        print(f"\033[31mConfig error: {e}{RESET}")
        sys.exit(1)

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
            print(f"""{DIM}Commands:
  /quit           — Exit the agent
  /clear          — Clear conversation history
  /model          — Show current provider and model
  /inspect        — Show every LLM call's input and output
  /clear-inspect  — Clear inspector records (independent of /clear)
  /help           — Show this help{RESET}""")
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
