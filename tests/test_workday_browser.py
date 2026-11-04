"""Playwright against local copies of Workday steps. Skipped without Playwright or Microsoft Edge."""

from contextlib import ExitStack
from pathlib import Path

import pytest

from hirejutsu import browser
from hirejutsu.applicant import Applicant
from hirejutsu.errors import HirejutsuError
from hirejutsu.workday import fill_step

PAGES = Path(__file__).parent / "fixtures" / "workday"
DETAILS = Applicant(
    first_name="Asha",
    last_name="Rao",
    email="asha@example.com",
    phone="9876543210",
    phone_code="+91",
    address={"line1": "12 MG Road", "city": "Pune", "state": "Maharashtra", "postal_code": "411001", "country": "India"},
    answers={"how_did_you_hear": "LinkedIn"},
)


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


def test_my_information_is_filled_in_the_browser(window):
    report = fill_step(open_page(window, "my-information.html"), "My Information", DETAILS)
    fields = by_id(window)
    assert {key: field.value for key, field in fields.items()} == {
        "source": "LinkedIn", "candidateIsPreviousWorker": "No", "country": "India", "legalName--firstName": "Asha",
        "legalName--lastName": "Rao", "legalName--firstNameLocal": "", "preferredCheck": "", "addressLine1": "12 MG Road",
        "city": "Pune", "countryRegion": "Maharashtra", "postalCode": "411001", "phoneType": "Mobile",
        "countryPhoneCode": "India (+91)", "phoneNumber": "9876543210", "extension": "",
    }
    assert [field.label for field in report.left] == ["Local Given Name(s)", "Phone Extension"]


def test_save_and_continue_is_never_clicked(window):
    fill_step(open_page(window, "my-information.html"), "My Information", DETAILS)
    assert window.tab.evaluate("document.body.dataset.next") is None


def test_an_older_page_is_filled_by_its_ids(window):
    page = open_page(window, "my-information-older.html")
    assert page.step() == "contactInformationPage"
    fill_step(page, "My Information", DETAILS)
    assert {key: field.value for key, field in by_id(page).items()} == {
        "sourceArea": "LinkedIn", "previousWorkerArea": "No", "firstNameArea": "Asha", "lastNameArea": "Rao",
        "lineArea": "12 MG Road", "cityArea": "Pune", "regionArea": "Maharashtra", "postalArea": "411001",
        "emailArea": "asha@example.com", "deviceArea": "Mobile", "numberArea": "9876543210",
    }
