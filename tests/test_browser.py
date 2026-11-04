import sys
from types import SimpleNamespace

import pytest

from hirejutsu import browser
from hirejutsu.errors import HirejutsuError


class FakeError(Exception):
    pass


class FakeContext:
    pages: list = []
    closed = False

    def set_default_timeout(self, milliseconds):
        self.timeout = milliseconds

    def close(self):
        self.closed = True


class FakeChromium:
    """Records how the browser was launched, or fails the launch with error."""

    def __init__(self, error=None):
        self.error = error
        self.launches = []
        self.context = FakeContext()

    def launch_persistent_context(self, folder, **options):
        self.launches.append((folder, options))
        if self.error:
            raise self.error
        return self.context


def fake_playwright(monkeypatch, chromium):
    class Driver:
        def __enter__(self):
            return SimpleNamespace(chromium=chromium)

        def __exit__(self, *exc):
            return False

    api = SimpleNamespace(sync_playwright=Driver, Error=FakeError)
    monkeypatch.setattr(browser, "playwright", lambda: api)


def settings(tmp_path, name="msedge"):
    return {"browser": name, "profile_folder": tmp_path / "browser", "max_skills": 10}


def test_without_playwright_you_are_told_to_install_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    with pytest.raises(HirejutsuError, match=r'pip install -e "\.\[workday\]"'):
        browser.playwright()


def test_edge_opens_in_a_window_with_its_own_profile(tmp_path, monkeypatch):
    chromium = FakeChromium()
    fake_playwright(monkeypatch, chromium)
    with browser.open_window(settings(tmp_path)) as page:
        assert page.context is chromium.context
    folder, options = chromium.launches[0]
    assert folder == str(tmp_path / "browser")
    assert (options["channel"], options["headless"]) == ("msedge", False)
    assert chromium.context.closed


def test_chromium_is_playwrights_own_browser(tmp_path, monkeypatch):
    chromium = FakeChromium()
    fake_playwright(monkeypatch, chromium)
    with browser.open_window(settings(tmp_path, "chromium")):
        pass
    assert chromium.launches[0][1]["channel"] is None


def test_a_browser_that_does_not_start_is_reported(tmp_path, monkeypatch):
    error = FakeError("BrowserType.launch_persistent_context: Chromium distribution 'msedge' is not found\nmore")
    fake_playwright(monkeypatch, FakeChromium(error))
    with pytest.raises(HirejutsuError, match="Cannot open Microsoft Edge: Chromium distribution 'msedge' is not found"):
        with browser.open_window(settings(tmp_path)):
            pass


def test_a_missing_chromium_says_how_to_get_it(tmp_path, monkeypatch):
    error = FakeError("Executable doesn't exist at C:\\ms-playwright\\chrome.exe\nplaywright install")
    fake_playwright(monkeypatch, FakeChromium(error))
    with pytest.raises(HirejutsuError, match="Run: playwright install chromium"):
        with browser.open_window(settings(tmp_path, "chromium")):
            pass
