"""Simulated tools - hardcoded tasks with realistic, fixed latency.

Why simulated? Because the whole point here is *latency*, and real tools
have unpredictable latency that would make the streaming-vs-non-streaming
comparison noisy and hard to reproduce. Each tool here just
`sleep`s for a fixed, well-known duration and returns canned output, so the
behaviour is easy to reason about.

These tools all model **slow, I/O-bound work** - reading files, running a
test suite, hitting the network, querying a database. I/O-bound work is
where streaming execution helps: a tool that starts mid-stream spends its
time *waiting*, overlapping the model's remaining token generation instead
of running after it.

The LATENCY dict is the single source of truth for "how slow" each tool is.
Tweak it and re-run a prompt to see the math change.
"""

import time

# How long each simulated tool "takes". Intentionally varied so that
# sum(durations) is much larger than max(durations) - that gap is the
# headroom the StreamingToolExecutor recovers via concurrency.
LATENCY = {
    "read_file": 1.2,
    "run_tests": 3.0,
    "web_search": 2.0,
    "lint_code": 1.5,
    "db_query": 2.4,
}


def _sleep(name: str) -> float:
    """Block for the tool's configured latency. Returns the latency used."""
    secs = LATENCY[name]
    time.sleep(secs)
    return secs


# ── read_file ────────────────────────────────────────────────────────────

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": (
        "Read the contents of a file from disk. Use this to inspect source "
        "code, config, or docs before changing them."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read."}
        },
        "required": ["path"],
    },
}


def handle_read_file(path: str) -> str:
    secs = _sleep("read_file")
    return (
        f"[simulated read of {path} - took {secs:.1f}s]\n"
        "def add(a, b):\n"
        "    return a + b\n"
    )


# ── run_tests ────────────────────────────────────────────────────────────

RUN_TESTS_SCHEMA = {
    "name": "run_tests",
    "description": (
        "Run the project's test suite and return a pass/fail summary. "
        "Slow - this is the kind of long task you want overlapped with others."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Optional test path or pattern. Defaults to the whole suite.",
            }
        },
        "required": [],
    },
}


def handle_run_tests(path: str = "tests/") -> str:
    secs = _sleep("run_tests")
    return f"[simulated test run on {path} - took {secs:.1f}s]\n42 passed, 0 failed in {secs:.1f}s"


# ── web_search ───────────────────────────────────────────────────────────

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the web and return the top results for a query.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."}
        },
        "required": ["query"],
    },
}


def handle_web_search(query: str) -> str:
    secs = _sleep("web_search")
    return (
        f"[simulated web search for {query!r} - took {secs:.1f}s]\n"
        "1. Streaming tool execution overlaps tool calls with generation.\n"
        "2. Concurrency turns sum(latency) into max(latency)."
    )


# ── lint_code ────────────────────────────────────────────────────────────

LINT_CODE_SCHEMA = {
    "name": "lint_code",
    "description": "Run the linter over a file or directory and report issues.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory to lint."}
        },
        "required": ["path"],
    },
}


def handle_lint_code(path: str) -> str:
    secs = _sleep("lint_code")
    return f"[simulated lint of {path} - took {secs:.1f}s]\nNo issues found."


# ── db_query ─────────────────────────────────────────────────────────────

DB_QUERY_SCHEMA = {
    "name": "db_query",
    "description": "Run a read-only SQL query against the database and return rows.",
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "The SQL query to run."}
        },
        "required": ["sql"],
    },
}


def handle_db_query(sql: str) -> str:
    secs = _sleep("db_query")
    return f"[simulated query {sql!r} - took {secs:.1f}s]\nuser_id | name\n1 | Ada\n2 | Linus"


# ── registration helper ──────────────────────────────────────────────────

SIMULATED_TOOLS = [
    (READ_FILE_SCHEMA, handle_read_file),
    (RUN_TESTS_SCHEMA, handle_run_tests),
    (WEB_SEARCH_SCHEMA, handle_web_search),
    (LINT_CODE_SCHEMA, handle_lint_code),
    (DB_QUERY_SCHEMA, handle_db_query),
]


def register_all(registry) -> None:
    """Register every simulated tool on the given ToolRegistry."""
    for schema, handler in SIMULATED_TOOLS:
        registry.register(schema, handler)
