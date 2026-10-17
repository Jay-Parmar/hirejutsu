"""ai test and ai explain commands."""

from rich.markup import escape
from rich.text import Text

from .. import ai
from ..errors import HirejutsuError


def register(sub) -> None:
    ai_parser = sub.add_parser("ai", help="use the optional AI second opinion")
    actions = ai_parser.add_subparsers(dest="action", metavar="action", required=True)

    parser = actions.add_parser("test", help="check the ai config with one tiny request")
    parser.set_defaults(func=check)


def check(app, args) -> int:
    settings = ai.load_settings(app.config)
    app.console.print(Text(f"Testing {settings['model']} from {settings['provider']} at {settings['base_url']}"))
    try:
        reply = ai.ask("Answer with one word.", "Say OK.", settings, ai.make_client(settings))
    except HirejutsuError as exc:
        app.console.print(f"[red]Failed:[/red] {escape(str(exc))}")
        return 1
    app.console.print(Text(f"It works. The model said: {reply.strip()}"))
    if not settings["enabled"]:
        app.console.print("Set ai.enabled to true in the config to use it in 'hirejutsu run'.")
    return 0
