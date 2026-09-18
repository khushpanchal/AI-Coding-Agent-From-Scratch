"""Provider registry — instantiates the Ollama provider from config."""

from agent.providers.base import BaseProvider


def get_provider(config: dict) -> BaseProvider:
    """Create and return the Ollama provider instance."""
    model = config["model"]
    host = config.get("ollama_host", "http://localhost:11434")

    from agent.providers.ollama import OllamaProvider
    return OllamaProvider(model=model, host=host)
