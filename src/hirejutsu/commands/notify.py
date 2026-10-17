"""notify command, also used by run to send the day's picks."""

from rich.markup import escape

from ..notify import picks_message, send_all


def send_picks(app, matches, day, files) -> None:
    print_sent(app.console, send_all(app.config, app.client, picks_message(matches, day, files)))


def print_sent(console, results: list[tuple[str, str]]) -> None:
    for name, error in results:
        if error:
            console.print(f"{name}: [red]failed:[/red] {escape(error)}")
        else:
            console.print(f"{name}: [green]sent[/green]")
