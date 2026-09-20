"""Background subagent manager — run subagents on daemon threads.

A *backgrounded subagent* is Phase-7's `run_subagent` (a child agent loop with
fresh context) running on a daemon thread instead of blocking the main loop.
`run` returns immediately with a task ID; when the child finishes, its summary
is pushed to a thread-safe mailbox that the agent loop drains before each LLM
call and injects into the conversation.

This is the asynchronous twin of the subagent: Phase 7 delegates *thinking* and
blocks the parent; background delegates the same thinking and doesn't. The
child runs with `quiet=True` so its token stream stays off the terminal — only
its summary comes back, through the mailbox. (No stdout plumbing needed: the
child loop simply doesn't print.)

A backgrounded subagent with a name and a persistent memory is what a Phase-9
teammate becomes; this is the seed of that idea.
"""

import threading
from collections import deque
from datetime import datetime

BACKGROUND_RUN_SCHEMA = {
    "name": "background_run",
    "description": (
        "Spawn a subagent in the background (non-blocking). Returns immediately "
        "with a task ID; the subagent works in its own fresh context and its "
        "summary is auto-injected when it finishes — so you can keep working "
        "meanwhile. Good for: self-contained subtasks like codebase analysis, "
        "isolated refactors, or wide multi-file searches. "
        "Types: 'explore' (READ-ONLY) or 'general' (full tools incl. write/edit, "
        "the default). Use check_background to poll status."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task for the background subagent to perform.",
            },
            "agent_type": {
                "type": "string",
                "enum": ["explore", "general"],
                "description": (
                    "'explore' has read-only tools (no write/edit); 'general' "
                    "(default) adds write/edit. Pick 'explore' only when the "
                    "task is purely read/analysis."
                ),
            },
        },
        "required": ["prompt"],
    },
}

CHECK_BACKGROUND_SCHEMA = {
    "name": "check_background",
    "description": "Check the status of background subagents. Shows running and finished tasks.",
    "parameters": {"type": "object", "properties": {}},
}


class BackgroundManager:
    """Runs subagents on daemon threads and collects their summaries."""

    def __init__(self, provider):
        self._provider = provider
        self._tasks: dict[int, dict] = {}  # id -> {prompt, agent_type, status, result, started_at}
        self._notifications: deque = deque()  # thread-safe mailbox of finished summaries
        self._lock = threading.Lock()
        self._next_id = 1

    def run(self, prompt: str, agent_type: str = "general") -> str:
        """Start a subagent in a background thread. Returns immediately."""
        with self._lock:
            task_id = self._next_id
            self._next_id += 1
            self._tasks[task_id] = {
                "prompt": prompt,
                "agent_type": agent_type,
                "status": "running",
                "result": None,
                "started_at": datetime.now().strftime("%H:%M:%S"),
            }

        threading.Thread(
            target=self._execute,
            args=(task_id, prompt, agent_type),
            daemon=True,
        ).start()

        return (
            f"Background subagent #{task_id} started ({agent_type}). "
            f"Its summary will be delivered automatically when it finishes."
        )

    def check(self) -> str:
        """Return status of all background subagents."""
        if not self._tasks:
            return "No background tasks."

        lines = ["Background tasks:"]
        for tid, task in sorted(self._tasks.items()):
            status = task["status"]
            desc = task["prompt"][:60]
            if status == "running":
                lines.append(f"  #{tid} [running] {desc} (started {task['started_at']})")
            elif status == "completed":
                lines.append(f"  #{tid} [done] {desc}")
                preview = (task["result"] or "")[:120]
                if preview:
                    lines.append(f"       {preview}")
            elif status == "error":
                lines.append(f"  #{tid} [error] {desc}: {task['result']}")
        return "\n".join(lines)

    def drain_notifications(self) -> list[str]:
        """Return and clear all pending finished-task notifications."""
        results = []
        while self._notifications:
            results.append(self._notifications.popleft())
        return results

    def _execute(self, task_id: int, prompt: str, agent_type: str):
        """Run the subagent loop on the background daemon thread."""
        # Lazy import avoids a circular import at module load time.
        from agent.parallel.subagent import run_subagent

        try:
            summary = run_subagent(self._provider, prompt, agent_type, quiet=True)
            status = "completed"
        except Exception as e:
            summary = f"Error: {e}"
            status = "error"

        task = self._tasks[task_id]
        task["status"] = status
        task["result"] = summary

        self._notifications.append(
            f"<background-result task_id='{task_id}'>\n"
            f"{summary}\n"
            f"</background-result>"
        )
