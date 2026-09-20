"""Three-layer context compression — keeps the agent working indefinitely.

Layer 1 (Micro): Every turn, replace old tool results with placeholders.
Layer 2 (Auto):  When tokens exceed threshold, summarize via LLM.
Layer 3 (Manual): Agent calls the compact tool explicitly.
"""

import json

# Rough token estimation: ~4 characters per token
TOKEN_RATIO = 4
AUTO_COMPACT_THRESHOLD = 100_000  # tokens
KEEP_RECENT_TOOLS = 3  # Number of recent tool results to preserve


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token count based on message content length."""
    return len(json.dumps(messages, default=str)) // TOKEN_RATIO


def micro_compact(messages: list[dict]) -> None:
    """Layer 1: Replace old tool results with short placeholders.

    Runs every turn. Keeps the last KEEP_RECENT_TOOLS tool result
    messages intact; replaces older ones with a summary line.
    Modifies messages in-place.
    """
    # Find indices of tool result messages
    tool_indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tool_indices.append(i)

    # Replace old tool results (keep the most recent ones)
    if len(tool_indices) <= KEEP_RECENT_TOOLS:
        return

    old_indices = tool_indices[:-KEEP_RECENT_TOOLS]
    for i in old_indices:
        messages[i]["content"] = "[Previous tool result — see context above]"


def should_auto_compact(messages: list[dict]) -> bool:
    """Check if automatic compaction should trigger."""
    return estimate_tokens(messages) > AUTO_COMPACT_THRESHOLD


def auto_compact(messages: list[dict], provider) -> list[dict]:
    """Layer 2: Summarize the entire conversation via LLM.

    Replaces all messages with a summary. Returns the new (compacted)
    message list.
    """
    # Ask the LLM to summarize
    summary_prompt = [
        {
            "role": "user",
            "content": (
                "Summarize the conversation so far in a concise paragraph. "
                "Focus on: what the user asked for, what was accomplished, "
                "what's still in progress, and any important context. "
                "Be specific about file names, tool results, and decisions made.\n\n"
                "Conversation:\n"
                + json.dumps(messages, default=str)[:30000]
            ),
        }
    ]

    try:
        response = provider.chat(
            messages=summary_prompt,
            system="You are a conversation summarizer. Be concise and factual.",
            max_tokens=1024,
        )
        summary = response.get("content", "Context was compressed.")
    except Exception:
        summary = "Previous conversation context was compressed due to length."

    return [
        {
            "role": "user",
            "content": f"[Context Summary — conversation was compressed]\n{summary}",
        },
        {
            "role": "assistant",
            "content": "Understood. I have the context from our previous conversation. How can I continue helping you?",
        },
    ]


def manual_compact(messages: list[dict], provider) -> list[dict]:
    """Layer 3: Same as auto_compact but triggered explicitly by the agent."""
    return auto_compact(messages, provider)


# ──────────────────────────────────────────────
# Compact Tool (for Layer 3 — manual trigger)
# ──────────────────────────────────────────────

COMPACT_SCHEMA = {
    "name": "compact",
    "description": (
        "Compress the conversation context by summarizing it. "
        "Use this when the conversation is getting long and you want to "
        "free up context space."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
}
