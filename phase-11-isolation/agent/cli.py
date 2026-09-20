"""CLI entry point — interactive REPL."""

import sys

from agent.core import inspector
from agent.core.config import get_config
from agent.core.loop import agent_loop
from agent.isolation.worktree import WORKTREE_SCHEMA, WorktreeManager
from agent.knowledge.skills import LOAD_SKILL_SCHEMA, SkillLoader
from agent.memory.agents_md import load_agents_md
from agent.memory.compression import (
    COMPACT_SCHEMA,
    estimate_tokens,
    manual_compact,
)
from agent.parallel.background import (
    BACKGROUND_RUN_SCHEMA,
    CHECK_BACKGROUND_SCHEMA,
    BackgroundManager,
)
from agent.parallel.subagent import SUBAGENT_SCHEMA, run_subagent
from agent.parallel.team import TEAM_SCHEMA, Team
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

For self-contained work that shouldn't fill your main context (large
file scans, isolated reviews), spawn a `subagent` and wait for its
summary. If you'd rather keep working while it runs, use `background_run`
instead — it spawns the same kind of isolated subagent on a background
thread and auto-injects its summary when done. Don't busy-poll with
`check_background`; use it only if the user explicitly asks for status.

When a goal splits into several independent parts, build an autonomous
`team`: `hire` a couple of teammates with roles, then break the goal into
a list of tasks and call `team` with action='run' and that `tasks` list.
The team self-distributes — each teammate pulls the next task from a
shared queue and works until the queue is empty, then you get all their
reports back. Don't hand-assign tasks to specific people; just hand over
the task list and let the team balance the work itself.

To try something in isolation — an experiment or an alternative
implementation — without touching the main workspace, create a
`worktree`: it gives you a separate folder on its own branch. Do the
experimental work there; the main workspace stays untouched.

Always read before editing. Use tools — don't describe them.\
"""


def print_banner(provider_name: str):
    print(f"""
{BOLD}╔══════════════════════════════════════════╗
║            AI Coding Agent               ║
║                Isolation                 ║
╚══════════════════════════════════════════╝{RESET}
{DIM}Provider: {provider_name}
Type /quit to exit, /help for commands.{RESET}
""")


def setup_tools(provider, messages_ref: list, tasks: TaskManager, skills: SkillLoader, bg: BackgroundManager, team: Team, worktrees: WorktreeManager) -> ToolRegistry:
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

    def handle_subagent(prompt: str, agent_type: str = "general") -> str:
        return run_subagent(provider, prompt, agent_type)

    registry.register(SUBAGENT_SCHEMA, handle_subagent)
    registry.register(BACKGROUND_RUN_SCHEMA, bg.run)
    registry.register(CHECK_BACKGROUND_SCHEMA, bg.check)
    registry.register(TEAM_SCHEMA, team.handle)
    registry.register(WORKTREE_SCHEMA, worktrees.handle)
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
    bg = BackgroundManager(provider)
    team = Team(provider)
    worktrees = WorktreeManager()

    agents_md = load_agents_md()
    if agents_md:
        system_prompt = SYSTEM_PROMPT_BASE + skills.get_system_prompt_section() + "\n\n" + agents_md
        print(f"{DIM}Loaded AGENTS.md project instructions.{RESET}")
    else:
        system_prompt = SYSTEM_PROMPT_BASE + skills.get_system_prompt_section()

    messages: list[dict] = []
    tools = setup_tools(provider, messages, tasks, skills, bg, team, worktrees)

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
  /team           — Show the team roster and who's working
  /worktrees      — List git worktrees (isolated workspaces)
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
        elif user_input == "/team":
            print(f"{DIM}{team.handle('status')}{RESET}")
            continue
        elif user_input == "/worktrees":
            print(f"{DIM}{worktrees.handle('list')}{RESET}")
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
                background_manager=bg,
            )
        except Exception as e:
            print(f"{RESET}\033[31mError: {e}\033[0m")
            if messages and messages[-1].get("role") == "user":
                messages.pop()


if __name__ == "__main__":
    main()
