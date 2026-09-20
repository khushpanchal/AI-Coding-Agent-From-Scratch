"""Teams — named, persistent teammates that a lead coordinates.

This is the end of a three-phase progression. Each phase added ONE property:

    Phase 7 (subagent):   delegate once and WAIT for a summary.
    Phase 8 (background): delegate once and DON'T wait — it runs on a thread.
    Phase 9 (team):       delegate REPEATEDLY to the SAME NAMED worker who
                          REMEMBERS — i.e. identity + memory.

A *teammate* is therefore just a background subagent that also has:
  - a name and a role (e.g. "Sam", the "backend engineer"), and
  - its own message history that PERSISTS across assignments — so it remembers
    what it did last time, which a disposable subagent cannot.

The main agent is the *lead*. It hires teammates, assigns them work (which runs
in parallel on daemon threads), then calls `wait` to gather everyone's reports
in one place. Communication is hub-and-spoke: teammates never talk to each
other, only to the lead. That one rule keeps the whole thing easy to follow.

Notice this file never imports or modifies the core agent loop's behaviour.
Phase 8 had to teach the loop to drain a mailbox; here the lead's explicit
`wait` does the gathering, so the loop from Phase 1 stays exactly as it was.
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
RESET = "\033[0m"

MAX_TEAMMATE_ITERATIONS = 30

TEAM_SCHEMA = {
    "name": "team",
    "description": (
        "Build and direct a team of named teammates who work in parallel. Each "
        "teammate is an independent agent with its own memory that persists "
        "across assignments. You are the lead; teammates report only to you.\n"
        "Actions:\n"
        "- 'hire': add a teammate (needs name + role, e.g. name='Sam', role='backend engineer').\n"
        "- 'assign': give a teammate a task (needs name + task). Returns immediately and runs "
        "in the background, so you can assign other teammates meanwhile.\n"
        "- 'wait': block until all working teammates finish, then collect their reports.\n"
        "- 'status': show the roster and who is working on what.\n"
        "Typical flow: hire a couple of teammates, assign each a task, then 'wait' to gather "
        "their results and combine them into your answer. Because a teammate keeps its memory, "
        "you can assign the same person a follow-up that builds on their earlier work."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["hire", "assign", "wait", "status"],
                "description": "The action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Teammate name (required for 'hire' and 'assign').",
            },
            "role": {
                "type": "string",
                "description": "Teammate's specialty, e.g. 'backend engineer' (required for 'hire').",
            },
            "task": {
                "type": "string",
                "description": "The work to give a teammate (required for 'assign').",
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
        self.messages: list[dict] = []  # persists across assignments — this is the memory
        self.tools = _make_teammate_tools()
        self.status = "idle"  # "idle" | "working"
        self.current_task = ""

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, the {self.role} on a small engineering team. "
            f"A lead assigns you tasks; complete each one using your tools.\n\n"
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
            "You may receive several tasks over time. Your earlier work stays in "
            "your memory, so build on what you have already done."
        )


class Team:
    """The roster the lead works with: hire, assign (parallel), wait, status."""

    def __init__(self, provider):
        self._provider = provider
        self._members: dict[str, Teammate] = {}
        self._reports: deque = deque()  # finished (name, summary) pairs waiting to be gathered
        self._lock = threading.Lock()

    def handle(self, action: str, name: str = "", role: str = "", task: str = "") -> str:
        if action == "hire":
            return self._hire(name, role)
        if action == "assign":
            return self._assign(name, task)
        if action == "wait":
            return self._wait()
        if action == "status":
            return self._status()
        return f"Error: unknown action '{action}'. Use: hire, assign, wait, status."

    def _hire(self, name: str, role: str) -> str:
        if not name or not role:
            return "Error: 'hire' needs both a name and a role (e.g. name='Sam', role='backend engineer')."
        if name in self._members:
            return f"Error: {name} is already on the team."
        self._members[name] = Teammate(name, role)
        return f"Hired {name} ({role}). Team is now: {', '.join(self._roster())}."

    def _assign(self, name: str, task: str) -> str:
        if not name or not task:
            return "Error: 'assign' needs both a name and a task."
        member = self._members.get(name)
        if member is None:
            return (
                f"Error: no teammate named '{name}'. Hire them first (action='hire'), "
                "or use action='status' to see the roster."
            )
        with self._lock:
            if member.status == "working":
                return (
                    f"Error: {name} is still working on a task. "
                    "Call action='wait' to gather results before assigning more."
                )
            member.status = "working"
            member.current_task = task
        member.messages.append({"role": "user", "content": task})
        threading.Thread(target=self._run, args=(member,), daemon=True).start()
        return (
            f"Assigned to {name}: {task}\n"
            f"({name} is now working in the background — assign others, then 'wait' to gather.)"
        )

    def _wait(self) -> str:
        with self._lock:
            working = any(m.status == "working" for m in self._members.values())
            pending = len(self._reports)
        if not working and pending == 0:
            return "No teammates are working, and there are no reports to gather."

        collected: list[tuple[str, str]] = []
        # Drain reports as they land (printing on THIS, the main, thread — so the
        # lines never interleave), and stop only once nobody is working and the
        # mailbox is empty.
        while True:
            for name, summary in self._drain():
                first = (summary.strip().splitlines() or ["(done)"])[0]
                print(f"{DIM}[{name}] ✓ {first[:80]}{RESET}")
                collected.append((name, summary))
            with self._lock:
                still_working = any(m.status == "working" for m in self._members.values())
                more = len(self._reports) > 0
            if not still_working and not more:
                break
            time.sleep(0.2)

        return self._format_reports(collected)

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
            if self._reports:
                lines.append(
                    f"  ({len(self._reports)} finished report(s) waiting — call action='wait' to gather)"
                )
        return "\n".join(lines)

    def _run(self, member: Teammate):
        """Run one teammate's agent loop on a daemon thread, then file its report."""
        # Lazy import avoids a circular import at module load time, and keeps this
        # file from depending on the loop at import time.
        from agent.core.loop import agent_loop

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
            self._reports.append((member.name, summary))

    def _drain(self) -> list[tuple[str, str]]:
        with self._lock:
            out = list(self._reports)
            self._reports.clear()
        return out

    def _roster(self) -> list[str]:
        return [f"{m.name} ({m.role})" for m in self._members.values()]

    def _format_reports(self, collected: list[tuple[str, str]]) -> str:
        if not collected:
            return "No reports gathered."
        blocks = [f"Gathered {len(collected)} report(s) from the team:\n"]
        for name, summary in collected:
            blocks.append(f"[from: {name}]\n{summary}\n")
        return "\n".join(blocks)


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
