"""CLAUDE.md loader — discovers and reads project instruction files.

Walks up from the current working directory to find CLAUDE.md files at
multiple scopes.  All discovered files are concatenated and injected into
the system prompt so the agent follows project-specific rules.

Lookup order (all are loaded, nearest-first):
    1. cwd/CLAUDE.md                — project-level
    2. each parent up to filesystem root
    3. ~/.claude/CLAUDE.md          — user-level (global defaults)
"""

from pathlib import Path

_HOME_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"


def _walk_up(start: Path) -> list[Path]:
    """Walk up from *start* collecting every CLAUDE.md found."""
    found: list[Path] = []
    current = start.resolve()
    while True:
        candidate = current / "CLAUDE.md"
        if candidate.is_file():
            found.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return found


def load_claude_md(workspace: Path | None = None) -> str:
    """Return the combined contents of all discovered CLAUDE.md files.

    Returns an empty string when no files are found.
    """
    workspace = (workspace or Path.cwd()).resolve()

    paths = _walk_up(workspace)

    if _HOME_CLAUDE_MD.is_file() and _HOME_CLAUDE_MD.resolve() not in {p.resolve() for p in paths}:
        paths.append(_HOME_CLAUDE_MD)

    if not paths:
        return ""

    sections: list[str] = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if text:
            sections.append(f"# Instructions from {p}\n\n{text}")

    return "\n\n---\n\n".join(sections)
