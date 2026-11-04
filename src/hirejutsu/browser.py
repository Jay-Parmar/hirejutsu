"""The browser window that Workday forms are filled in, driven by Playwright.

Playwright comes with the optional workday extra, so it is imported only when a window opens.
"""

from contextlib import contextmanager
from functools import cache
from importlib import resources

from .errors import HirejutsuError
from .workday import Field, WindowClosed

CHANNELS = {"msedge": "msedge", "chrome": "chrome", "chromium": None}
NAMES = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium"}
# Milliseconds a click or a key press may take before it counts as failed.
TIMEOUT = 5000
# Milliseconds a job page may take to open.
PAGE_TIMEOUT = 60000


def playwright():
    """Playwright's sync API."""
    try:
        from playwright import sync_api
    except ImportError as exc:
        raise HirejutsuError('Playwright is not installed. Run: pip install -e ".[workday]"') from exc
    return sync_api


@contextmanager
def open_window(settings: dict, headless: bool = False):
    """A browser window with a profile of its own, as a WorkdayPage. The window closes after."""
    api = playwright()
    with api.sync_playwright() as driver:
        try:
            context = driver.chromium.launch_persistent_context(
                str(settings["profile_folder"]),
                channel=CHANNELS[settings["browser"]],
                headless=headless,
                no_viewport=True,
                args=["--start-maximized"],
            )
        except api.Error as exc:
            raise HirejutsuError(launch_error(settings["browser"], exc)) from exc
        context.set_default_timeout(TIMEOUT)
        try:
            yield WorkdayPage(context, api.Error)
        finally:
            try:
                context.close()
            except api.Error:
                pass


def launch_error(browser: str, exc: Exception) -> str:
    """What to say when the browser does not start."""
    if browser == "chromium" and "playwright install" in str(exc):
        return "Playwright's Chromium is not installed. Run: playwright install chromium"
    return f"Cannot open {NAMES[browser]}: {first_line(exc)}"


def first_line(exc: Exception) -> str:
    """The first line of a Playwright error, without the call that failed, which it starts with."""
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0].split(": ", 1)[-1]


@cache
def script() -> str:
    """data/workday.js, which reads the page from the inside."""
    return resources.files("hirejutsu").joinpath("data", "workday.js").read_text(encoding="utf-8")


class WorkdayPage:
    """The open Workday tab, as the page object workday.py fills."""

    def __init__(self, context, error: type):
        self.context = context
        # Playwright's error class, raised when the page changes or closes under a call.
        self.error = error

    @property
    def tab(self):
        """The newest open tab, as the job site may open the application in a new one."""
        tabs = [tab for tab in self.context.pages if not tab.is_closed()]
        if not tabs:
            raise WindowClosed
        return tabs[-1]

    @property
    def url(self) -> str:
        return self.tab.url

    def goto(self, url: str) -> None:
        try:
            self.tab.goto(url, timeout=PAGE_TIMEOUT)
        except self.error as exc:
            raise HirejutsuError(f"Cannot open {url}: {first_line(exc)}") from exc

    def wait(self, seconds: float) -> None:
        self.call(lambda tab: tab.wait_for_timeout(seconds * 1000))

    def step(self) -> str:
        return self.run("step") or ""

    def fields(self) -> list[Field]:
        rows = self.run("fields") or []
        return [Field(**{**row, "ids": tuple(row["ids"]), "options": tuple(row["options"])}) for row in rows]

    def run(self, action: str, argument=None):
        """One action of workday.js. None while the page is changing, as when the next step loads."""
        return self.call(lambda tab: tab.evaluate(script(), [action, argument]))

    def call(self, do):
        """do(tab), or None when Playwright fails. Raises WindowClosed once the window is gone."""
        tab = self.tab
        try:
            return do(tab)
        except self.error:
            if tab.is_closed():
                raise WindowClosed from None
            return None
