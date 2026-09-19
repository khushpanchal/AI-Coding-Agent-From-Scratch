"""Subagents — spawn child agents with fresh context for isolated tasks.

The parent's growing message history stays clean. The child starts with
empty messages, works up to 30 iterations, and returns only a text summary.
"""

from agent.providers.base import BaseProvider
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

MAX_SUBAGENT_ITERATIONS = 30

SUBAGENT_SCHEMA = {
    "name": "subagent",
    "description": (
        "Spawn a child agent with fresh context to handle a subtask. "
        "The child works independently and returns a text summary. "
        "Use this for tasks that need focused context without polluting "
        "the main conversation. Types: 'explore' (READ-ONLY — for "
        "analysis, summaries, or searches that don't touch files) or "
        "'general' (full tools including write/edit). Use 'general' if "
        "the task involves any file creation or modification — 'explore' "
        "subagents will silently fail to write."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task for the child agent to perform.",
            },
            "agent_type": {
                "type": "string",
                "enum": ["explore", "general"],
                "description": (
                    "Type of subagent. 'explore' has read-only tools "
                    "(no write_file / edit_file). 'general' has all "
                    "tools and is the default — pick 'explore' only "
                    "when you are sure the task is purely read/analysis."
                ),
            },
        },
        "required": ["prompt"],
    },
}


def _make_subagent_tools(agent_type: str = "general") -> ToolRegistry:
    """Create a tool registry for the subagent."""
    registry = ToolRegistry()
    registry.register(BASH_SCHEMA, handle_bash)
    registry.register(READ_FILE_SCHEMA, handle_read_file)
    registry.register(LIST_FILES_SCHEMA, handle_list_files)
    registry.register(SEARCH_FILES_SCHEMA, handle_search_files)

    if agent_type == "general":
        registry.register(WRITE_FILE_SCHEMA, handle_write_file)
        registry.register(EDIT_FILE_SCHEMA, handle_edit_file)

    return registry


def run_subagent(
    provider: BaseProvider,
    prompt: str,
    agent_type: str = "general",
) -> str:
    """Run a subagent with fresh context and return its text output.

    The subagent gets its own message list (context isolation).
    Only the final text response is returned to the parent.
    """
    # Import here to avoid circular imports
    from agent.core.loop import agent_loop

    tools = _make_subagent_tools(agent_type)
    messages = [{"role": "user", "content": prompt}]

    system = (
        "You are a focused subagent. Complete the given task efficiently.\n\n"
        "When done, provide a brief outcome-focused summary of WHAT you accomplished. "
        "Do NOT include:\n"
        "- Tool call syntax or names (e.g. 'write_file(...)', '[tool: ...]')\n"
        "- Verbatim file contents or code you wrote\n"
        "- Byte counts, line counts, or other tool-result boilerplate\n"
        "- A step-by-step replay of your actions\n\n"
        "The parent agent only sees your summary — keep it high-level "
        "(1-3 sentences) describing the result, not the process."
    )

    try:
        agent_loop(
            provider=provider,
            messages=messages,
            tools=tools,
            system=system,
            max_iterations=MAX_SUBAGENT_ITERATIONS,
        )
    except Exception as e:
        return f"Subagent error: {e}"

    # Extract the last assistant message as the summary
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                return content
            # Handle Anthropic-style content blocks
            if isinstance(content, list):
                texts = []
                for block in content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block["text"])
                if texts:
                    return "\n".join(texts)

    return "Subagent completed but produced no text output."
