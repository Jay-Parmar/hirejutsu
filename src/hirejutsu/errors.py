class HirejutsuError(Exception):
    """Error with a message meant for the user."""


class ConfigError(HirejutsuError):
    """Invalid or unreadable config."""
