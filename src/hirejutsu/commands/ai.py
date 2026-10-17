"""ai test and ai explain commands."""

from rich.markup import escape
from rich.text import Text

from .. import ai
from ..errors import HirejutsuError
from ..resume import load_profile


def register(sub) -> None:
    ai_parser = sub.add_parser("ai", help="use the optional AI second opinion")
    actions = ai_parser.add_subparsers(dest="action", metavar="action", required=True)

    parser = actions.add_parser("test", help="check the ai config with one tiny request")
    parser.set_defaults(func=check)

    parser = actions.add_parser("explain", help="ask how well one saved job fits your resume")
    parser.add_argument("job_id", type=int, help="the job's ID, as shown in the picks table")
    parser.set_defaults(func=explain)


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


def explain(app, args) -> int:
    settings = ai.load_settings(app.config)
    if not settings["enabled"]:
        raise HirejutsuError("The AI second opinion is off. Set ai.enabled to true in the config first.")
    job = app.store.get_job(args.job_id)
    if job is None:
        raise HirejutsuError(f"No job with id {args.job_id}")
    profile = load_profile(app.config)
    app.console.print(Text(f"{job.title} at {job.company}", style="bold"))
    app.console.print(Text(ai.explain(job, profile, settings, ai.make_client(settings))))
    return 0
