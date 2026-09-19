"""TaskManager — in-memory task list with dependencies and a stuck-item reminder.

Tasks live in memory for the duration of the session. Each task can have
optional `blocked_by` dependencies; at most one task may be in_progress at
a time. If the active task stays in_progress for many rounds, a reminder
prompts the model to break it down or note progress — phrased so that
prematurely marking it completed isn't the path of least resistance.
"""

TASK_SCHEMA = {
    "name": "task",
    "description": (
        "Manage your task list. Use this to plan multi-step work and track "
        "progress, with optional dependencies between tasks. "
        "Actions: 'create' (add a new task), 'update' (change status or description), "
        "'list' (show all tasks), 'get' (show one task's details), 'delete' (remove). "
        "Statuses: pending, in_progress, completed. "
        "Only one task can be in_progress at a time. "
        "Use blocked_by on create to express dependencies; a task whose blockers "
        "aren't completed cannot be started."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "list", "get", "delete"],
                "description": "The action to perform.",
            },
            "subject": {
                "type": "string",
                "description": "Brief title (required for 'create').",
            },
            "description": {
                "type": "string",
                "description": "Detailed description (optional for 'create' and 'update').",
            },
            "task_id": {
                "type": "integer",
                "description": "Task ID (required for 'update', 'get', 'delete').",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed"],
                "description": "New status (for 'update').",
            },
            "blocked_by": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Task IDs that must complete before this task can start (optional, for 'create').",
            },
        },
        "required": ["action"],
    },
}

MAX_TASKS = 50
SOFT_NAG_AGE = 8   # First reminder when the active task has been in_progress this many rounds
HARD_NAG_AGE = 16  # Stronger reminder if still in_progress after this many rounds

STATUS_ICONS = {
    "pending": "[ ]",
    "in_progress": "[>]",
    "completed": "[x]",
}


class TaskManager:
    def __init__(self):
        self._tasks: dict[int, dict] = {}
        self._next_task_id = 1
        self._round = 0

    def handle(
        self,
        action: str,
        subject: str = "",
        description: str = "",
        task_id: int = -1,
        status: str = "",
        blocked_by: list[int] | None = None,
    ) -> str:
        if action == "create":
            if not subject:
                return "Error: 'subject' is required for action='create'."
            return self._create(subject, description, blocked_by)
        if action == "update":
            if task_id == -1:
                return (
                    "Error: 'task_id' is required for action='update'. "
                    "Call action='list' first if you don't know the ID, "
                    "then pass it as an integer (e.g. task_id=1)."
                )
            return self._update(
                task_id,
                status or None,
                description if description else None,
            )
        if action == "list":
            return self._list()
        if action == "get":
            if task_id == -1:
                return (
                    "Error: 'task_id' is required for action='get'. "
                    "Call action='list' first to see available IDs."
                )
            return self._get(task_id)
        if action == "delete":
            if task_id == -1:
                return (
                    "Error: 'task_id' is required for action='delete'. "
                    "Call action='list' first to see available IDs."
                )
            return self._delete(task_id)
        return f"Error: Unknown action '{action}'. Use: create, update, list, get, delete."

    def tick(self) -> str | None:
        """Called each loop iteration. Reminder fires based on how long the active task has been in_progress."""
        self._round += 1
        active_id = next(
            (tid for tid, t in self._tasks.items() if t["status"] == "in_progress"),
            None,
        )
        if active_id is None:
            return None
        active = self._tasks[active_id]
        started_at = active.get("started_at")
        if started_at is None:
            return None
        age = self._round - started_at
        if age == HARD_NAG_AGE:
            return (
                f"<reminder>Task #{active_id} \"{active['subject']}\" has been in progress "
                f"for {HARD_NAG_AGE} rounds — this is unusually long. Options: "
                f"(a) break it down by creating smaller sub-tasks, "
                f"(b) note why it's taking longer and continue, "
                f"(c) mark it completed only if the work is actually done."
                f"</reminder>"
            )
        if age == SOFT_NAG_AGE:
            return (
                f"<reminder>Task #{active_id} \"{active['subject']}\" has been in progress "
                f"for {SOFT_NAG_AGE} rounds. If you're still working on it, keep going. "
                f"If it has grown larger than expected, consider splitting it into "
                f"smaller sub-tasks."
                f"</reminder>"
            )
        return None

    def list_all(self) -> str:
        """Public accessor for the /tasks slash command."""
        return self._list()

    def _create(self, subject: str, description: str = "", blocked_by: list[int] | None = None) -> str:
        if not subject:
            return "Error: 'subject' is required for create action."
        if len(self._tasks) >= MAX_TASKS:
            return f"Error: Maximum {MAX_TASKS} tasks reached. Delete completed tasks first."

        if blocked_by:
            invalid = [bid for bid in blocked_by if bid not in self._tasks]
            if invalid:
                invalid_str = ", ".join(f"#{i}" for i in invalid)
                return (
                    f"Error: 'blocked_by' references non-existent task(s): {invalid_str}. "
                    "You can only block on tasks that already exist. "
                    "Create the dependency tasks first, then create this one with their IDs."
                )

        task_id = self._next_task_id
        self._next_task_id += 1
        task = {
            "id": task_id,
            "subject": subject,
            "description": description,
            "status": "pending",
            "blocked_by": list(blocked_by or []),
            "blocks": [],
            "started_at": None,
        }

        if blocked_by:
            for dep_id in blocked_by:
                dep = self._tasks.get(dep_id)
                if dep and task_id not in dep["blocks"]:
                    dep["blocks"].append(task_id)

        self._tasks[task_id] = task
        return f"Created task #{task_id}: {subject}\n{self._format_task(task)}"

    def _update(
        self,
        task_id: int,
        status: str | None = None,
        description: str | None = None,
    ) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Error: Task #{task_id} not found."

        if status:
            if status not in STATUS_ICONS:
                return f"Error: Invalid status '{status}'. Use: pending, in_progress, completed."

            if status in ("in_progress", "completed"):
                active_blockers = self._active_blockers(task)
                if active_blockers:
                    blockers = ", ".join(f"#{bid}" for bid in active_blockers)
                    return f"Error: Task #{task_id} is blocked by: {blockers}"

            if status == "in_progress":
                # Mutual exclusion: demote any other in_progress task to pending
                for tid, other in self._tasks.items():
                    if tid != task_id and other["status"] == "in_progress":
                        other["status"] = "pending"
                        other["started_at"] = None
                # Start the clock only on transition INTO in_progress, not on re-assertion
                if task["status"] != "in_progress":
                    task["started_at"] = self._round
            else:
                task["started_at"] = None

            task["status"] = status

        if description is not None:
            task["description"] = description

        return f"Updated task #{task_id}.\n{self._format_task(task)}"

    def _list(self) -> str:
        if not self._tasks:
            return "No tasks."
        lines = ["Tasks:"]
        for t in sorted(self._tasks.values(), key=lambda x: x["id"]):
            icon = STATUS_ICONS.get(t["status"], "[ ]")
            active = self._active_blockers(t)
            blocked = f" (blocked by: {active})" if active else ""
            lines.append(f"  #{t['id']} {icon} {t['subject']}{blocked}")
        return "\n".join(lines)

    def _get(self, task_id: int) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Error: Task #{task_id} not found."
        return self._format_task(task)

    def _delete(self, task_id: int) -> str:
        task = self._tasks.get(task_id)
        if not task:
            return f"Error: Task #{task_id} not found."

        for other in self._tasks.values():
            if task_id in other["blocked_by"]:
                other["blocked_by"].remove(task_id)
            if task_id in other.get("blocks", []):
                other["blocks"].remove(task_id)

        del self._tasks[task_id]
        return f"Deleted task #{task_id}: {task['subject']}"

    def _active_blockers(self, task: dict) -> list[int]:
        """Return blocker IDs whose tasks aren't yet completed."""
        return [
            bid for bid in task["blocked_by"]
            if (bt := self._tasks.get(bid)) and bt["status"] != "completed"
        ]

    def _format_task(self, task: dict) -> str:
        lines = [
            f"Task #{task['id']}: {task['subject']}",
            f"  Status: {task['status']}",
        ]
        if task["description"]:
            lines.append(f"  Description: {task['description']}")
        active = self._active_blockers(task)
        if active:
            lines.append(f"  Blocked by: {active}")
        if task["blocks"]:
            lines.append(f"  Blocks: {task['blocks']}")
        return "\n".join(lines)
