"""notify command, also used by run to send the day's picks."""

from datetime import date, datetime

from rich.markup import escape

from ..notify import SENDERS, picks_message, sample_message, send_all


def register(sub) -> None:
    parser = sub.add_parser("notify", help="send the picks to your notify channels again")
    parser.add_argument("--test", action="store_true", help="send a short test message instead")
    parser.add_argument("--day", type=date.fromisoformat, help="send the picks of another day (YYYY-MM-DD)")
    parser.add_argument("--channel", choices=list(SENDERS), help="send to this channel only")
    parser.set_defaults(func=notify)


def notify(app, args) -> int:
    if args.test:
        message = sample_message()
    else:
        day = args.day or datetime.now().astimezone().date()
        matches = app.store.picks(day)
        if not matches:
            app.console.print(f"No picks for {day}. Run 'hirejutsu run' first.")
            return 1
        message = picks_message(matches, day, sorted(app.config.reports_dir.glob(f"{day.isoformat()}.*")))
    results = send_all(app.config, app.client, message, only=args.channel)
    if not results:
        target = f"notify.{args.channel}" if args.channel else "a channel under notify"
        app.console.print(f"Nothing sent. Turn on {target} in config.yaml with enabled: true.")
        return 1
    print_sent(app.console, results)
    return 1 if any(error for _, error in results) else 0


def send_picks(app, matches, day, files) -> None:
    print_sent(app.console, send_all(app.config, app.client, picks_message(matches, day, files)))


def print_sent(console, results: list[tuple[str, str]]) -> None:
    for name, error in results:
        if error:
            console.print(f"{name}: [red]failed:[/red] {escape(error)}")
        else:
            console.print(f"{name}: [green]sent[/green]")
