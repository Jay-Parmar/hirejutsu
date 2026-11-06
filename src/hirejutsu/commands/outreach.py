"""outreach command: drafts emails to recruiters about the day's picks. It never sends them."""

from datetime import date, datetime

from rich.style import Style
from rich.table import Column, Table
from rich.text import Text

from .. import ai, outreach
from ..applicant import EMAIL, load_applicant
from ..contacts import Finder
from ..errors import HirejutsuError
from ..models import Match, Profile
from ..resume import load_profile
from .report import show_saved
from .track import add_ids, named_jobs


def register(sub) -> None:
    parser = sub.add_parser("outreach", help="find recruiters for the day's picks and draft emails to them")
    parser.add_argument("--day", type=date.fromisoformat, help="another day (YYYY-MM-DD), default today")
    parser.add_argument("-n", type=int, metavar="LIMIT", help="write about at most this many picks")
    parser.add_argument("--open", action="store_true", help="open the HTML page in your browser")
    parser.set_defaults(func=draft_emails)
    actions = parser.add_subparsers(dest="action", metavar="action")

    action = actions.add_parser("sent", help="note that you emailed someone about a job")
    add_ids(action, nargs=1)
    action.add_argument("addresses", nargs="+", metavar="ADDRESS", help="the addresses you wrote to")
    action.set_defaults(func=record_sent)


def draft_emails(app, args) -> int:
    day = args.day or datetime.now().astimezone().date()
    matches = app.store.picks(day)
    if not matches:
        app.console.print(f"No picks for {day}. Run 'hirejutsu run' first.")
        return 1
    settings = outreach.load_settings(app.config)
    chosen = picks_to_write(app, matches, settings)
    chosen = chosen[:args.n] if args.n else chosen
    if not chosen:
        app.console.print("No picks to write about.")
        return 0
    drafts = write_drafts(app, chosen, settings)
    print_drafts(app.console, drafts, day)
    show_saved(app, outreach.save_drafts(drafts, app.config, day), args.open)
    return 0


def picks_to_write(app, matches: list[Match], settings: dict) -> list[Match]:
    """The picks worth an email, saying which were left out and why."""
    kept = outreach.picks_to_write(matches, settings)
    if len(kept) < len(matches):
        app.console.print(f"Left out {len(matches) - len(kept)} of {len(matches)} picks because they come from "
                          "job boards. Add their sources to outreach.sources to write about them too.")
    fresh = [match for match in kept if not outreach.emailed(app.store, match.job.id)]
    if len(fresh) < len(kept):
        app.console.print(f"Left out {len(kept) - len(fresh)} you already emailed about.")
    return fresh


def write_drafts(app, matches: list[Match], settings: dict) -> list[outreach.Draft]:
    profile = load_profile(app.config)
    applicant = load_applicant(app.config)
    if not applicant.name:
        app.console.print("Your name is missing from the sign off. Run 'hirejutsu applicant --edit' to add it.")
    key = outreach.search_key(settings)
    if settings["search"] and not key:
        app.console.print(f"outreach.search is {settings['search']}, but {settings['search_key_env']} is not set, "
                          "so there is no search for recruiters.")
    finder = Finder(app.client, key)
    drafts = []
    with app.console.status(f"Looking for contacts at {len(matches)} companies..."):
        for match in matches:
            contacts = finder.contacts(match.job)
            people = finder.recruiters(match.job.company)
            drafts.append(outreach.draft(match, contacts, people, profile, applicant, settings))
    if settings["ai"]:
        rewrite_with_ai(app, drafts, profile)
    return drafts


def rewrite_with_ai(app, drafts: list[outreach.Draft], profile: Profile) -> None:
    """Let the AI of the ai section rewrite each body for its job. After a failure the rest keep the template."""
    settings = ai.load_settings(app.config)
    client = ai.make_client(settings)
    with app.console.status("Asking the AI to rewrite the drafts..."):
        for draft in drafts:
            try:
                draft.body = ai.rewrite_email(draft.match.job, profile, draft.body, settings, client)
            except Exception as exc:  # The drafts from the template are good enough to send.
                app.console.print(Text(f"The AI could not rewrite the drafts, so they stay as written: {exc}"))
                return


def print_drafts(console, drafts: list[outreach.Draft], day: date) -> None:
    # Addresses cannot wrap, so the job and company columns get narrower instead.
    table = Table("ID", "Job", "Company", Column("Write to", no_wrap=True), "How sure",
                  title=f"Recruiter emails for {day}")
    for draft in drafts:
        job = draft.match.job
        sure = draft.best.confidence if draft.best else ""
        table.add_row(str(job.id), Text(job.title, style=Style(link=job.url)), Text(job.company),
                      Text(draft.to or "nobody found"), sure)
    console.print(table)


def record_sent(app, args) -> int:
    wrong = [address for address in args.addresses if not EMAIL.fullmatch(address)]
    if wrong:
        raise HirejutsuError(f"{wrong[0]} is not an email address")
    jobs = named_jobs(app, args)
    for job in jobs:
        app.store.add_note(job.id, outreach.sent_note(args.addresses))
        app.console.print(Text(f"Noted that you emailed {', '.join(args.addresses)} about job {job.id}: "
                               f"{job.title} at {job.company}"))
    return 0 if jobs else 1
