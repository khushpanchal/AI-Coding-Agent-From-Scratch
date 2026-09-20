"""Autonomous team — teammates that PULL their own work from a shared queue.

The progression, each phase adding ONE property:

    Phase 7 (subagent):   delegate once and WAIT for a summary.
    Phase 8 (background): delegate once and DON'T wait — it runs on a thread.
    Phase 9 (team):       delegate REPEATEDLY to the SAME NAMED worker who
                          REMEMBERS — identity + memory. But the lead PUSHES:
                          it hand-assigns each task to a named teammate and
                          waits at a barrier, so a free teammate can't grab the
                          next task while another is still busy.
    Phase 10 (this file): the team is AUTONOMOUS. You drop a GOAL's tasks into a
                          shared queue and every teammate runs a pull-loop —
                          grab the next free task, do it, grab the next — until
                          the queue is empty. Nobody hand-assigns; the free
                          worker decides what's next, the instant it's free. The
                          team self-distributes and self-balances, and it stops
                          on an OBJECTIVE condition: the queue is empty.

Push (phase 9): the LEAD decides who's next, only at coarse barriers.
Pull (phase 10): the FREE TEAMMATE decides what's next, immediately.

Still hub-and-spoke (teammates never talk to each other) and still memory-
keeping (each teammate's message history persists across the tasks it pulls).
The core agent loop is untouched — the new idea is just the shared queue plus
the per-teammate pull-loop.
"""

import threading
import time
from collections import deque

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

DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

MAX_TEAMMATE_ITERATIONS = 30

TEAM_SCHEMA = {
    "name": "team",
    "description": (
        "Build and run an autonomous team. You are the lead. Each teammate is an "
        "independent agent with its own memory. Teammates do NOT talk to each other.\n"
        "Actions:\n"
        "- 'hire': add a teammate (needs name + role, e.g. name='Sam', role='backend engineer').\n"
        "- 'run': hand the team a list of tasks (needs 'tasks'). The tasks go into a shared "
        "queue and every teammate pulls work from it in parallel — grab the next free task, do "
        "it, grab the next — until the queue is empty. You do NOT assign tasks to specific "
        "people; the team self-distributes. This call blocks until all tasks are done, then "
        "returns every teammate's reports.\n"
        "- 'status': show the roster, who is working on what, and how many tasks remain.\n"
        "Typical flow: 'hire' a couple of teammates, break the goal into independent tasks, then "
        "'run' that task list and combine the reports you get back."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["hire", "run", "status"],
                "description": "The action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Teammate name (required for 'hire').",
            },
            "role": {
                "type": "string",
                "description": "Teammate's specialty, e.g. 'backend engineer' (required for 'hire').",
            },
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "The goal broken into independent tasks (required for 'run'). "
                    "The team pulls these from a shared queue until empty."
                ),
            },
        },
        "required": ["action"],
    },
}


def _make_teammate_tools() -> ToolRegistry:
    """A teammate gets the full tool set — read, search, run commands, write, edit."""
    registry = ToolRegistry()
    registry.register(BASH_SCHEMA, handle_bash)
    registry.register(READ_FILE_SCHEMA, handle_read_file)
    registry.register(LIST_FILES_SCHEMA, handle_list_files)
    registry.register(SEARCH_FILES_SCHEMA, handle_search_files)
    registry.register(WRITE_FILE_SCHEMA, handle_write_file)
    registry.register(EDIT_FILE_SCHEMA, handle_edit_file)
    return registry


class Teammate:
    """One named team member: a role, a tool set, and a memory that persists."""

    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self.messages: list[dict] = []  # persists across the tasks it pulls — the memory
        self.tools = _make_teammate_tools()
        self.status = "idle"  # "idle" | "working"
        self.current_task = ""

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, the {self.role} on a small engineering team. "
            f"You are given one task at a time; complete each one using your tools.\n\n"
            "Working rules:\n"
            "- Actually do the work with tools — if the task names a file, create "
            "or change that exact file. Don't just describe what you would do.\n"
            "- To CHANGE an existing file, read_file it first, then use edit_file "
            "to apply only that change. Never use write_file to overwrite a whole "
            "file when you were asked to add or modify one part — you will destroy "
            "the rest.\n"
            "- Before you report done, read_file the file back and confirm your "
            "change is present AND the existing content is still intact.\n\n"
            "When done, give a brief outcome-focused summary (1-3 sentences) of "
            "WHAT you accomplished — not how. Do not include tool-call syntax, "
            "verbatim file contents, or a step-by-step replay; the lead only sees "
            "your summary.\n\n"
            "Your earlier work stays in your memory, so build on what you have "
            "already done."
        )


class Team:
    """An autonomous roster: hire teammates, then run a shared task queue they drain."""

    def __init__(self, provider):
        self._provider = provider
        self._members: dict[str, Teammate] = {}
        self._queue: deque = deque()    # shared task queue — teammates pull from this
        self._events: deque = deque()   # ("pulled", name, task) / ("done", name, task, summary)
        self._lock = threading.Lock()

    def handle(self, action: str = "", name: str = "", role: str = "", tasks=None) -> str:
        if action == "hire":
            return self._hire(name, role)
        if action == "run":
            return self._run_team(tasks)
        if action == "status":
            return self._status()
        return f"Error: unknown action '{action}'. Use: hire, run, status."

    def _hire(self, name: str, role: str) -> str:
        if not name or not role:
            return "Error: 'hire' needs both a name and a role (e.g. name='Sam', role='backend engineer')."
        if name in self._members:
            return f"Error: {name} is already on the team."
        self._members[name] = Teammate(name, role)
        return f"Hired {name} ({role}). Team is now: {', '.join(self._roster())}."

    def _run_team(self, tasks) -> str:
        """Load the queue, start every teammate pulling, block until it's drained."""
        if not self._members:
            return "Error: no teammates yet. Hire at least one first (action='hire')."
        queue = _normalize_tasks(tasks)
        if not queue:
            return "Error: 'run' needs a non-empty 'tasks' list (the goal broken into tasks)."

        with self._lock:
            self._queue.extend(queue)
            self._events.clear()
        print(f"{BOLD}[team] {len(queue)} task(s) queued; {len(self._members)} teammate(s) pulling…{RESET}")

        # Every teammate runs its own pull-loop in parallel.
        for member in self._members.values():
            threading.Thread(target=self._work_loop, args=(member,), daemon=True).start()

        # Main thread: print events as they land (so lines never interleave) and
        # stop once the queue is empty AND everyone is idle AND nothing's pending.
        collected: list[tuple[str, str, str]] = []
        while True:
            for ev in self._drain_events():
                if ev[0] == "pulled":
                    print(f"{DIM}[{ev[1]}] pulled: {ev[2][:60]}{RESET}")
                else:  # ("done", name, task, summary)
                    first = (ev[3].strip().splitlines() or ["(done)"])[0]
                    print(f"{DIM}[{ev[1]}] ✓ {first[:70]}{RESET}")
                    collected.append((ev[1], ev[2], ev[3]))
            with self._lock:
                drained = (
                    not self._queue
                    and all(m.status == "idle" for m in self._members.values())
                    and not self._events
                )
            if drained:
                break
            time.sleep(0.1)

        print(f"{BOLD}[team] queue empty — all tasks done{RESET}")
        return self._format_reports(collected)

    def _work_loop(self, member: Teammate):
        """A teammate's pull-loop: grab the next task, do it, repeat until empty."""
        # Lazy import avoids a circular import at module load time.
        from agent.core.loop import agent_loop

        while True:
            with self._lock:
                if not self._queue:
                    break  # objective stop: nothing left to pull
                task = self._queue.popleft()
                member.status = "working"
                member.current_task = task
                self._events.append(("pulled", member.name, task))

            member.messages.append({"role": "user", "content": task})
            try:
                agent_loop(
                    provider=self._provider,
                    messages=member.messages,
                    tools=member.tools,
                    system=member.system_prompt(),
                    max_iterations=MAX_TEAMMATE_ITERATIONS,
                    quiet=True,
                )
                summary = _last_text(member.messages) or "(completed, but produced no summary)"
            except Exception as e:
                summary = f"Error: {e}"

            with self._lock:
                member.status = "idle"
                member.current_task = ""
                self._events.append(("done", member.name, task, summary))

        with self._lock:
            member.status = "idle"
            member.current_task = ""

    def _status(self) -> str:
        if not self._members:
            return "No teammates hired yet. Use action='hire' with a name and role."
        with self._lock:
            lines = ["Team:"]
            for m in self._members.values():
                if m.status == "working":
                    lines.append(f"  {m.name} ({m.role}) — working on: {m.current_task[:60]}")
                else:
                    lines.append(f"  {m.name} ({m.role}) — idle")
            if self._queue:
                lines.append(f"  ({len(self._queue)} task(s) still in the queue)")
        return "\n".join(lines)

    def _drain_events(self) -> list[tuple]:
        with self._lock:
            out = list(self._events)
            self._events.clear()
        return out

    def _roster(self) -> list[str]:
        return [f"{m.name} ({m.role})" for m in self._members.values()]

    def _format_reports(self, collected: list[tuple[str, str, str]]) -> str:
        if not collected:
            return "No tasks were completed."
        blocks = [f"The team completed {len(collected)} task(s):\n"]
        for name, task, summary in collected:
            blocks.append(f"[{name}] {task}\n{summary}\n")
        return "\n".join(blocks)


def _normalize_tasks(tasks) -> list[str]:
    """Accept a list of tasks, or a single newline-separated string, → list[str]."""
    if isinstance(tasks, str):
        return [t.strip() for t in tasks.splitlines() if t.strip()]
    if isinstance(tasks, list):
        return [str(t).strip() for t in tasks if str(t).strip()]
    return []


def _last_text(messages: list[dict]) -> str:
    """Return the last assistant text in a message list (handles content blocks)."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                texts = []
                for block in content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block["text"])
                if texts:
                    return "\n".join(texts)
    return ""
