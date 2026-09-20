"""Configuration loader - resolves Ollama settings.

This project is a small, local AI agent (CLI + Ollama + agent loop)
built around ONE idea: **Streaming Tool Execution**.

The agent runs tools with the StreamingToolExecutor (agent/core/executor.py):
it starts each tool the instant its call appears in the model's stream (what
Claude Code does), while the model is still generating. Tools run in parallel.

Every turn also reports what the classic non-streaming approach (wait for the
whole response, then run the tools) would have cost on the same response, so
the saving is visible directly - no second run, no model-variance noise.
"""

MODEL = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"


def get_config() -> dict:
    """Return resolved configuration dict."""
    return {
        "provider": "ollama",
        "model": MODEL,
        "ollama_host": OLLAMA_HOST,
    }
