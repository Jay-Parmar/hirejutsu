"""init and config commands."""

from ..config import CONFIG_NAME, init_home, load_config
from ..desktop import edit_file


def register(sub) -> None:
    parser = sub.add_parser("init", help="create the data folder and a starter config")
    parser.add_argument("--force", action="store_true", help="overwrite an existing config")
    parser.set_defaults(func=init)

    parser = sub.add_parser("config", help="show the config path or open it")
    parser.add_argument("--edit", action="store_true", help="open the config in your editor")
    parser.set_defaults(func=config)


def init(app, args) -> int:
    path = app.home / CONFIG_NAME
    if init_home(app.home, force=args.force):
        app.console.print(f"Created {path}")
    else:
        app.console.print(f"{path} already exists, use --force to overwrite it")
    app.console.print(f"Next: put your resume in {app.home} and edit the config.")
    return 0


def config(app, args) -> int:
    path = app.home / CONFIG_NAME
    if not path.exists():
        app.console.print(f"No config at {path}. Run 'hirejutsu init' first.")
        return 1
    if args.edit:
        edit_file(path)
        return 0
    load_config(app.home)
    app.console.print(f"{path} is valid")
    return 0
