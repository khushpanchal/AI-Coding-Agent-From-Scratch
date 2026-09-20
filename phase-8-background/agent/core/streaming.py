"""Streaming handler — prints tokens to terminal as they arrive."""

import sys


def print_stream(stream_generator, quiet: bool = False) -> dict:
    """Consume a provider's chat_stream() and print text in real-time.

    Returns the final complete response dict from the 'done' event.

    When `quiet` is True the stream is still fully consumed (so we still get
    the final response) but nothing is written to the terminal. A backgrounded
    subagent runs quietly so its token stream doesn't interleave with the main
    loop's output — only its final summary comes back.
    """
    final_response = None

    for event in stream_generator:
        if event["type"] == "text":
            if not quiet:
                sys.stdout.write(event["content"])
                sys.stdout.flush()

        elif event["type"] == "tool_call":
            # In Phase 1 we just have chat, no tools yet.
            # This will be used starting Phase 2.
            pass

        elif event["type"] == "done":
            final_response = event.get("response", {})

    # Newline after streamed text
    if not quiet:
        print()

    return final_response or {"role": "assistant", "content": "", "tool_calls": [], "stop_reason": "end_turn"}
