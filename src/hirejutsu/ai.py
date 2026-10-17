"""Optional AI second opinion on the best matches."""

from .config import Config

AI_DEFAULTS = {
    "enabled": False,
    "provider": "anthropic",
    "model": "",
    "base_url": "",
    "api_key_env": "",
    "candidates": 30,
    "batch_size": 10,
    "weight": 0.5,
    "max_resume_chars": 8000,
    "max_description_chars": 3000,
}

PROVIDERS = {
    "anthropic": {
        "model": "claude-haiku-5-5",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "model": "gpt-5-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
}


def load_settings(config: Config) -> dict:
    """The ai section, with a blank model, base_url or api_key_env taken from the provider."""
    settings = config.section("ai", AI_DEFAULTS)
    for key, value in PROVIDERS.get(settings["provider"], {}).items():
        settings[key] = settings[key] or value
    return settings
