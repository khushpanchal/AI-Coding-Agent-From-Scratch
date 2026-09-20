"""Isolation — give the agent separate git worktrees to work in.

A *worktree* is a second working folder backed by the same git repo, checked
out to its own branch. Two worktrees are two independent directories: a file
written in one cannot touch the other. That's filesystem isolation — distinct
from the context isolation a subagent already has (its own message history).

Phase 9/10 teammates all shared ONE folder, so parallel work only stayed safe
when each task hit a different file. A worktree fixes that at the filesystem
level: you can try an experiment, or an alternative implementation, in its own
folder without ever touching the main workspace.

This wrapper uses only the basic git worktree commands:

    git worktree add worktrees/<name> -b <name>   # make an isolated folder + branch
    git worktree list                             # show them all

The agent never runs `git init` — isolation assumes you're already in a git
repo with a base commit (we return a friendly error if you're not).
"""

import subprocess
from pathlib import Path

WORKTREE_SCHEMA = {
    "name": "worktree",
    "description": (
        "Create and list git worktrees — separate working folders, each on its own "
        "branch, backed by the same repo. Use a worktree to try something in isolation "
        "(an experiment, an alternative implementation) without touching the main "
        "workspace.\n"
        "Actions:\n"
        "- 'create': make a new worktree (needs 'name'). Creates the folder "
        "worktrees/<name> checked out to a new branch named <name>.\n"
        "- 'list': show all worktrees and their branches."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list"],
                "description": "The action to perform.",
            },
            "name": {
                "type": "string",
                "description": "Worktree and branch name (required for 'create'), e.g. 'feature-exp'.",
            },
        },
        "required": ["action"],
    },
}


class WorktreeManager:
    """Wraps the basic `git worktree` commands. Assumes cwd is a git repo."""

    def __init__(self, base_dir: str | None = None):
        self._base = Path(base_dir or ".").resolve()

    def handle(self, action: str = "", name: str = "") -> str:
        if action == "create":
            return self._create(name)
        if action == "list":
            return self._list()
        return f"Error: unknown action '{action}'. Use: create, list."

    def _create(self, name: str) -> str:
        if not name:
            return "Error: 'create' needs a 'name' (e.g. name='feature-exp')."
        if not self._is_git_repo():
            return (
                "Error: this directory isn't a git repo, so there's nothing to isolate "
                "from. Run `git init` and make a base commit first, then try again."
            )
        rel = f"worktrees/{name}"
        ok, out = self._git("worktree", "add", rel, "-b", name)
        if not ok:
            return f"Error creating worktree '{name}': {out}"
        return (
            f"Created worktree '{name}' at {rel}/ on a new branch '{name}'. "
            "It's an independent folder — work in it without touching the main workspace."
        )

    def _list(self) -> str:
        ok, out = self._git("worktree", "list")
        if not ok:
            return f"Error: {out}"
        return out or "(no worktrees)"

    def _is_git_repo(self) -> bool:
        ok, out = self._git("rev-parse", "--is-inside-work-tree")
        return ok and out.strip() == "true"

    def _git(self, *args: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self._base,
                capture_output=True,
                text=True,
            )
            out = (result.stdout + result.stderr).strip()
            return result.returncode == 0, out
        except Exception as e:
            return False, str(e)
