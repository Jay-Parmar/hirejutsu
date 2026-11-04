"""Playwright against local copies of Workday steps. Skipped without Playwright or Microsoft Edge."""

from contextlib import ExitStack
from pathlib import Path

import pytest

from hirejutsu import browser
from hirejutsu.errors import HirejutsuError

PAGES = Path(__file__).parent / "fixtures" / "workday"


def only_local_files(route):
    """Nothing in these tests may come from the internet."""
    if route.request.url.startswith("file:"):
        route.continue_()
    else:
        route.abort()


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    pytest.importorskip("playwright.sync_api")
    settings = {"browser": "msedge", "profile_folder": tmp_path_factory.mktemp("browser"), "max_skills": 10}
    with ExitStack() as stack:
        try:
            page = stack.enter_context(browser.open_window(settings, headless=True))
        except HirejutsuError as exc:
            pytest.skip(str(exc))
        page.context.route("**/*", only_local_files)
        yield page


def open_page(window, name: str):
    """One of the test pages, in a fresh tab."""
    old = list(window.context.pages)
    window.context.new_page()
    for tab in old:
        tab.close()
    window.goto((PAGES / name).as_uri())
    return window


def by_id(window) -> dict:
    return {field.ids[0]: field for field in window.fields()}


def test_a_page_that_does_not_open_is_reported(window):
    with pytest.raises(HirejutsuError, match="Cannot open .*missing.html"):
        open_page(window, "missing.html")


def test_the_step_comes_from_the_progress_bar(window):
    assert open_page(window, "my-information.html").step() == "current step 2 of 6 My Information"


def test_fields_are_read_with_their_ids_labels_and_kinds(window):
    fields = by_id(open_page(window, "my-information.html"))
    first = fields["legalName--firstName"]
    assert (first.label, first.kind, first.value, first.required, first.section) == (
        "Given Name(s)", "text", "", True, "Legal Name",
    )
    assert (fields["source"].kind, fields["source"].value, fields["source"].required) == ("select", "", True)
    assert fields["country"].value == "India"
    assert fields["candidateIsPreviousWorker"].kind == "radio"
    assert fields["candidateIsPreviousWorker"].options == ("Yes", "No")
    assert fields["countryPhoneCode"].kind == "prompt"
    assert fields["preferredCheck"].kind == "checkbox"
    assert fields["legalName--lastName"].required is False


def test_the_box_only_robots_fill_in_is_left_out(window):
    fields = by_id(open_page(window, "my-information.html"))
    assert "website" not in fields
    assert not any("beecatcher" in field.ids for field in fields.values())
