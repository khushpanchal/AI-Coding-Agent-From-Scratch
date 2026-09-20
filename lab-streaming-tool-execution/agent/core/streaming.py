"""Streaming output - prints model tokens to the terminal as they arrive.

Consuming the stream and printing it are two separate jobs here: the
executor (executor.py) owns consuming the stream - because it also needs to
act on `tool_call` events the instant they appear - while this module just
provides the tiny callback that paints text on screen. The executor calls
`write_text(chunk)` for every text chunk and `write_text("\\n")` once the
stream ends.
"""

import sys


def write_text(chunk: str) -> None:
    """Write a streamed text chunk to stdout immediately (no buffering)."""
    sys.stdout.write(chunk)
    sys.stdout.flush()
