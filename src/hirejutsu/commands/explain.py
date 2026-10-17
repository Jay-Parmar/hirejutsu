"""explain command."""

from datetime import datetime

from rich.table import Table
from rich.text import Text

from ..daily import candidates, ranking_settings
from ..errors import HirejutsuError
from ..ranking import breakdown
from ..resume import load_profile


def register(sub) -> None:
    parser = sub.add_parser("explain", help="show how one job scores against your resume")
    parser.add_argument("job_id", type=int, help="job id, as shown by run, today and top")
    parser.set_defaults(func=explain)


def explain(app, args) -> int:
    job = app.store.get_job(args.job_id)
    if job is None:
        raise HirejutsuError(f"No job with id {args.job_id}")
    now = datetime.now().astimezone()
    result = breakdown(job, candidates(app.store, now), load_profile(app.config), ranking_settings(app.config), now)
    console = app.console
    console.print(Text(f"{job.title} at {job.company} (id {job.id})"))
    console.print(f"Score {result.score:.2f}")
    table = Table("Part", "Score", "Weight")
    for name, value in result.parts.items():
        table.add_row(name, f"{value:.2f}", f"{result.weights[name]:.2f}")
    console.print(table)
    console.print("Filters")
    for name, problem in result.checks:
        status = f"failed, {problem}" if problem else "passed"
        console.print(Text(f"  {name}: {status}"))
    if result.reasons:
        console.print("Reasons")
        for reason in result.reasons:
            console.print(Text(f"  - {reason}"))
    return 0
