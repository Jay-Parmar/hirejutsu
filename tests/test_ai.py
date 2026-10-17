from pathlib import Path

from hirejutsu import ai
from hirejutsu.config import Config


def settings(**values):
    return ai.load_settings(Config({"ai": values}, Path(".")))


def test_settings_default_to_anthropic_and_off():
    defaults = settings()
    assert defaults["enabled"] is False
    assert (defaults["provider"], defaults["model"], defaults["base_url"], defaults["api_key_env"]) == (
        "anthropic", "claude-haiku-5-5", "https://api.anthropic.com", "ANTHROPIC_API_KEY",
    )


def test_settings_fill_in_openai_defaults():
    openai = settings(provider="openai")
    assert (openai["model"], openai["base_url"], openai["api_key_env"]) == (
        "gpt-5-mini", "https://api.openai.com/v1", "OPENAI_API_KEY",
    )


def test_settings_keep_values_from_the_config():
    ollama = settings(provider="openai", base_url="http://localhost:11434/v1", model="llama3.1", candidates=12)
    assert (ollama["base_url"], ollama["model"], ollama["candidates"]) == ("http://localhost:11434/v1", "llama3.1", 12)
