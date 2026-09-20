"""Tool registry - register tools and dispatch calls by name.

The registry stays strategy-agnostic: it just runs a tool and returns a
string. *When* and *how concurrently* tools run is decided entirely by the
executor (see agent/core/executor.py). That separation is the whole point -
the same tools behave very differently under the two executors without any
change here.
"""

from typing import Callable

from agent.core import inspector


class ToolRegistry:
    """Central registry for all agent tools.

    Each tool has:
    - A schema (name, description, parameters) sent to the LLM
    - A handler function that executes the tool
    """

    def __init__(self):
        self._schemas: dict[str, dict] = {}
        self._handlers: dict[str, Callable] = {}

    def register(self, schema: dict, handler: Callable):
        """Register a tool with its schema and handler."""
        name = schema["name"]
        self._schemas[name] = schema
        self._handlers[name] = handler

    @property
    def schemas(self) -> list[dict]:
        """Return all tool schemas (sent to the LLM)."""
        return list(self._schemas.values())

    def dispatch(self, name: str, arguments: dict) -> str:
        """Execute a tool by name and return the result as a string.

        Validates arguments against the tool's schema before invoking the
        handler. Schema mismatches return self-correcting error strings so
        the model can recover. Every dispatch is recorded for /inspect.

        NOTE: this method is thread-safe to call concurrently - the
        StreamingToolExecutor invokes it from multiple worker threads at
        once. The simulated tools have no shared mutable state, and
        inspector.record_tool only appends to a list (atomic under CPython's
        GIL), so concurrent dispatch is fine for this project.
        """
        result = self._dispatch(name, arguments)
        inspector.record_tool(name, arguments, result)
        return result

    def _dispatch(self, name: str, arguments: dict) -> str:
        handler = self._handlers.get(name)
        if not handler:
            return f"Error: Unknown tool '{name}'"

        params = self._schemas[name].get("parameters", {})
        allowed = set(params.get("properties", {}).keys())
        required = params.get("required", [])

        missing = [p for p in required if p not in arguments]
        if missing:
            return (
                f"Error: Tool '{name}' missing required parameter(s): "
                f"{', '.join(missing)}."
            )

        unexpected = [k for k in arguments if k not in allowed]
        if unexpected:
            return (
                f"Error: Tool '{name}' got unexpected parameter(s): "
                f"{', '.join(unexpected)}. "
                f"Allowed: {', '.join(sorted(allowed)) if allowed else '(none)'}."
            )

        return handler(**arguments)
