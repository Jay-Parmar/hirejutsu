"""The browser window that Workday forms are filled in, driven by Playwright.

Playwright comes with the optional workday extra, so it is imported only when a window opens.
"""

from contextlib import contextmanager

from .errors import HirejutsuError

CHANNELS = {"msedge": "msedge", "chrome": "chrome", "chromium": None}
NAMES = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium"}
# Milliseconds a click or a key press may take before it counts as failed.
TIMEOUT = 5000


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
    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    # Playwright starts its messages with the call that failed.
    return f"Cannot open {NAMES[browser]}: {first.split(': ', 1)[-1]}"


class WorkdayPage:
    """The open Workday tab, as the page object workday.py fills."""

    def __init__(self, context, error: type):
        self.context = context
        # Playwright's error class, raised when the page changes or closes under a call.
        self.error = error
