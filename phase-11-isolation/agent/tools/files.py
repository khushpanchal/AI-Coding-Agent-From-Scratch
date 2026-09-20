"""File tools — read, write, edit, list (glob), search (grep)."""

import fnmatch
import os
import re
from pathlib import Path

from agent.tools.safety import WORKSPACE, safe_path, truncate_output

# ──────────────────────────────────────────────
# Tool Schemas
# ──────────────────────────────────────────────

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": (
        "Read the contents of a file. Returns the file content with line numbers. "
        "Use this to understand existing code before modifying it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file (relative to workspace).",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based). Optional.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read. Optional, defaults to 2000.",
            },
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": (
        "Create a new file or overwrite an existing file with the given content. "
        "Parent directories are created automatically."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file (relative to workspace).",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
}

EDIT_FILE_SCHEMA = {
    "name": "edit_file",
    "description": (
        "Edit a file by replacing an exact string match with new content. "
        "The old_string must match exactly (including whitespace and indentation). "
        "Use read_file first to see the current content."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file (relative to workspace).",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to find and replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The string to replace it with.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
}

LIST_FILES_SCHEMA = {
    "name": "list_files",
    "description": (
        "List files matching a glob pattern. "
        "Examples: '**/*.py' (all Python files), 'src/**/*.ts' (TypeScript in src/), "
        "'*.json' (JSON in current dir)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files (e.g., '**/*.py').",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (relative to workspace). Defaults to workspace root.",
            },
        },
        "required": ["pattern"],
    },
}

SEARCH_FILES_SCHEMA = {
    "name": "search_files",
    "description": (
        "Search file contents using a regex pattern (like grep). "
        "Returns matching lines with file paths and line numbers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for in file contents.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (relative to workspace). Defaults to workspace root.",
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob pattern to filter which files to search (e.g., '*.py'). Optional.",
            },
        },
        "required": ["pattern"],
    },
}


# ──────────────────────────────────────────────
# Tool Handlers
# ──────────────────────────────────────────────

def handle_read_file(path: str, offset: int = 1, limit: int = 2000) -> str:
    """Read a file with line numbers."""
    try:
        target = safe_path(path)
    except ValueError as e:
        return f"Error: {e}"
    if not target.is_file():
        return f"Error: File not found — {path}"

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return f"Error: Cannot read binary file — {path}"

    start = max(0, offset - 1)
    end = start + limit
    selected = lines[start:end]

    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i:>6}\t{line}")

    result = "\n".join(numbered)
    if not result:
        return "(empty file)"
    return truncate_output(result)


def handle_write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories."""
    try:
        target = safe_path(path)
    except ValueError as e:
        return f"Error: {e}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {path}"


def handle_edit_file(path: str, old_string: str, new_string: str) -> str:
    """Replace an exact string in a file."""
    try:
        target = safe_path(path)
    except ValueError as e:
        return f"Error: {e}"
    if not target.is_file():
        return f"Error: File not found — {path}"

    content = target.read_text(encoding="utf-8")
    count = content.count(old_string)

    if count == 0:
        return f"Error: old_string not found in {path}. Use read_file to check the current content."
    if count > 1:
        return (
            f"Error: old_string found {count} times in {path}. "
            "Provide more surrounding context to make it unique."
        )

    new_content = content.replace(old_string, new_string, 1)
    target.write_text(new_content, encoding="utf-8")
    return f"Edited {path} — replaced 1 occurrence."


def handle_list_files(pattern: str, path: str = "") -> str:
    """List files matching a glob pattern."""
    try:
        search_dir = safe_path(path) if path else WORKSPACE
    except ValueError as e:
        return f"Error: {e}"

    if not search_dir.is_dir():
        return f"Error: Directory not found — {path}"

    matches = sorted(search_dir.glob(pattern))
    # Filter to files only, make paths relative
    files = []
    for m in matches:
        if m.is_file():
            try:
                files.append(str(m.relative_to(WORKSPACE)))
            except ValueError:
                continue

    if not files:
        return f"No files matching '{pattern}' in {path or '.'}"

    # Cap at 200 results
    result = "\n".join(files[:200])
    if len(files) > 200:
        result += f"\n... and {len(files) - 200} more files"
    return result


def handle_search_files(pattern: str, path: str = "", file_pattern: str = "") -> str:
    """Search file contents with regex."""
    try:
        search_dir = safe_path(path) if path else WORKSPACE
    except ValueError as e:
        return f"Error: {e}"

    if not search_dir.is_dir():
        return f"Error: Directory not found — {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex — {e}"

    matches = []
    max_matches = 100

    for root, dirs, filenames in os.walk(search_dir):
        # Skip hidden and common non-source directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv")]

        effective_pattern = file_pattern.removeprefix("**/") if file_pattern else ""
        for filename in filenames:
            if effective_pattern and not fnmatch.fnmatch(filename, effective_pattern):
                continue

            filepath = Path(root) / filename
            try:
                content = filepath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    rel = filepath.relative_to(WORKSPACE)
                    matches.append(f"{rel}:{line_num}: {line.strip()}")
                    if len(matches) >= max_matches:
                        break

            if len(matches) >= max_matches:
                break
        if len(matches) >= max_matches:
            break

    if not matches:
        return f"No matches for pattern '{pattern}'"

    result = "\n".join(matches)
    if len(matches) == max_matches:
        result += f"\n... (limited to {max_matches} results)"
    return result
