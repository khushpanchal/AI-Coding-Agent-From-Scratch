"""AGENTS.md loader — discovers and reads project instruction files.

Walks up from the current working directory to find AGENTS.md files at
multiple scopes.  All discovered files are concatenated and injected into
the system prompt so the agent follows project-specific rules.

Lookup order (all are loaded, nearest-first):
    1. cwd/AGENTS.md                — project-level
    2. each parent up to filesystem root
    3. ~/.agent/AGENTS.md           — user-level (global defaults)
"""

from pathlib import Path

_HOME_AGENTS_MD = Path.home() / ".agent" / "AGENTS.md"


def _walk_up(start: Path) -> list[Path]:
    """Walk up from *start* collecting every AGENTS.md found."""
    found: list[Path] = []
    current = start.resolve()
    while True:
        candidate = current / "AGENTS.md"
        if candidate.is_file():
            found.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return found


def load_agents_md(workspace: Path | None = None) -> str:
    """Return the combined contents of all discovered AGENTS.md files.

    Returns an empty string when no files are found.
    """
    workspace = (workspace or Path.cwd()).resolve()

    paths = _walk_up(workspace)

    if _HOME_AGENTS_MD.is_file() and _HOME_AGENTS_MD.resolve() not in {p.resolve() for p in paths}:
        paths.append(_HOME_AGENTS_MD)

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
