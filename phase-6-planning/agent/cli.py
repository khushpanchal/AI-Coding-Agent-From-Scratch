"""CLI entry point — interactive REPL."""

import sys

from agent.core import inspector
from agent.core.config import get_config
from agent.core.loop import agent_loop
from agent.knowledge.skills import LOAD_SKILL_SCHEMA, SkillLoader
from agent.memory.agents_md import load_agents_md
from agent.memory.compression import (
    COMPACT_SCHEMA,
    estimate_tokens,
    manual_compact,
)
from agent.planning.tasks import TASK_SCHEMA, TaskManager
from agent.providers.registry import get_provider
from agent.tools.bash import BASH_SCHEMA, handle_bash
from agent.tools.files import (
    EDIT_FILE_SCHEMA,
    LIST_FILES_SCHEMA,
    READ_FILE_SCHEMA,
    SEARCH_FILES_SCHEMA,
    WRITE_FILE_SCHEMA,
    handle_edit_file,
    handle_list_files,
    handle_read_file,
    handle_search_files,
    handle_write_file,
)
from agent.tools.registry import ToolRegistry

CYAN = "\033[36m"
GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


SYSTEM_PROMPT_BASE = """\
You are a helpful AI coding agent.

For simple one-step requests, act directly. For multi-step or complex
work, plan first with the `task` tool:
- Create your tasks BEFORE starting any work, not after.
- Mark each task in_progress when you begin it, completed as soon as
  it's done — don't leave finished work in pending or in_progress.
- Don't create tasks retroactively to log work you already finished.
  Either plan up-front or skip the task tool entirely.

If your work matches a known skill (code review, agent building, etc.),
load the relevant skill with `load_skill` first to get task-specific
guidance before doing the work.

Always read before editing. Use tools — don't describe them.\
"""


def print_banner(provider_name: str):
    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║            AI Coding Agent               ║
║      Planning & Task Management          ║
╚══════════════════════════════════════════╝{RESET}
{DIM}Provider: {provider_name}
Type /quit to exit, /help for commands.{RESET}
""")


def setup_tools(provider, messages_ref: list, tasks: TaskManager, skills: SkillLoader) -> ToolRegistry:
    """Register all available tools."""
    registry = ToolRegistry()
    registry.register(BASH_SCHEMA, handle_bash)
    registry.register(READ_FILE_SCHEMA, handle_read_file)
    registry.register(WRITE_FILE_SCHEMA, handle_write_file)
    registry.register(EDIT_FILE_SCHEMA, handle_edit_file)
    registry.register(LIST_FILES_SCHEMA, handle_list_files)
    registry.register(SEARCH_FILES_SCHEMA, handle_search_files)

    def handle_compact() -> str:
        new_messages = manual_compact(messages_ref, provider)
        messages_ref.clear()
        messages_ref.extend(new_messages)
        return "Context compressed."

    registry.register(COMPACT_SCHEMA, handle_compact)
    registry.register(TASK_SCHEMA, tasks.handle)
    registry.register(LOAD_SKILL_SCHEMA, skills.load)
    return registry


def main():
    try:
        config = get_config()
    except ValueError as e:
        print(f"\033[31mConfig error: {e}{RESET}")
        sys.exit(1)

    provider = get_provider(config)
    print_banner(provider.name)

    tasks = TaskManager()
    skills = SkillLoader()

    agents_md = load_agents_md()
    if agents_md:
        system_prompt = SYSTEM_PROMPT_BASE + skills.get_system_prompt_section() + "\n\n" + agents_md
        print(f"{DIM}Loaded AGENTS.md project instructions.{RESET}")
    else:
        system_prompt = SYSTEM_PROMPT_BASE + skills.get_system_prompt_section()

    messages: list[dict] = []
    tools = setup_tools(provider, messages, tasks, skills)

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
  /compact        — Manually compress context
  /tokens         — Show estimated token count
  /tasks          — Show the task board
  /debug          — Dump raw message history (role + first 80 chars)
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
        elif user_input == "/compact":
            if not messages:
                print(f"{DIM}Nothing to compact.{RESET}")
            else:
                new = manual_compact(messages, provider)
                messages.clear()
                messages.extend(new)
                print(f"{DIM}Context compressed.{RESET}")
            continue
        elif user_input == "/tokens":
            tokens = estimate_tokens(messages)
            print(f"{DIM}Estimated tokens: ~{tokens:,}{RESET}")
            continue
        elif user_input == "/debug":
            if not messages:
                print(f"{DIM}(no messages){RESET}")
            else:
                for i, m in enumerate(messages):
                    content = str(m.get("content", ""))[:80].replace("\n", " ")
                    print(f"{DIM}  [{i:>3}] {m.get('role', '?'):<10} {content}{RESET}")
            continue
        elif user_input == "/tasks":
            print(f"{DIM}{tasks.list_all()}{RESET}")
            continue

        inspector.start_turn(user_input)
        messages.append({"role": "user", "content": user_input})

        try:
            agent_loop(
                provider=provider,
                messages=messages,
                tools=tools,
                system=system_prompt,
                task_manager=tasks,
            )
        except Exception as e:
            print(f"{RESET}\033[31mError: {e}\033[0m")
            if messages and messages[-1].get("role") == "user":
                messages.pop()


if __name__ == "__main__":
    main()
