"""Configuration loader — resolves Ollama settings."""
MODEL = "qwen2.5:7b-instruct"
OLLAMA_HOST = "http://localhost:11434"

def get_config() -> dict:
    """Return resolved configuration dict."""
    return {
        "provider": "ollama",
        "model": MODEL,
        "ollama_host": OLLAMA_HOST,
    }
