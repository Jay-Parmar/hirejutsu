"""Playwright against local copies of Workday steps. Skipped without Playwright or Microsoft Edge."""

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pytest

from hirejutsu import browser
from hirejutsu.applicant import Applicant, Position, School
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
EXPERIENCE = replace(
    DETAILS,
    links={"linkedin": "https://www.linkedin.com/in/asha", "github": "https://github.com/asha"},
    work=[
        Position("Backend Engineer", "Acme", "Pune", "2021-04", "", "Built the payments API."),
        Position("Developer", "Globex", "Mumbai", "2018-07", "2021-03"),
    ],
    education=[School("Pune University", "B.E.", "Computer Engineering", "2014", "2018", "8.1")],
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


def test_my_experience_is_filled_in_the_browser(window, tmp_path):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n%%EOF\n")
    page = open_page(window, "my-experience.html")
    fill_step(page, "My Experience", EXPERIENCE, skills=["Python", "Kubernetes", "AWS"], resume=resume)
    assert {(field.section, field.entry, field.label): field.value for field in page.fields()} == {
        ("Work Experience", 1, "Job Title"): "Backend Engineer",
        ("Work Experience", 1, "Company"): "Acme",
        ("Work Experience", 1, "Location"): "Pune",
        ("Work Experience", 1, "I currently work here"): "I currently work here",
        ("Work Experience", 1, "From"): "04/2021",
        ("Work Experience", 1, "To"): "",
        ("Work Experience", 1, "Role Description"): "Built the payments API.",
        ("Work Experience", 2, "Job Title"): "Developer",
        ("Work Experience", 2, "Company"): "Globex",
        ("Work Experience", 2, "Location"): "Mumbai",
        ("Work Experience", 2, "I currently work here"): "",
        ("Work Experience", 2, "From"): "07/2018",
        ("Work Experience", 2, "To"): "03/2021",
        ("Work Experience", 2, "Role Description"): "",
        ("Education", 1, "School or University"): "Pune University",
        ("Education", 1, "Degree"): "BE",
        ("Education", 1, "Field of Study"): "Computer Engineering",
        ("Education", 1, "Overall Result (GPA)"): "8.1",
        ("Education", 1, "From"): "2014",
        ("Education", 1, "To (Actual or Expected)"): "2018",
        ("Skills", 0, "Type to Add Skills"): "Python, AWS",
        ("Resume/CV", 0, "Upload a file (5MB max)"): "uploaded",
        ("Websites", 1, "URL"): "https://github.com/asha",
        ("Social Network URLs", 0, "LinkedIn"): "https://www.linkedin.com/in/asha",
    }


def test_questions_are_answered_in_the_browser(window):
    answers = {"needs_sponsorship": "No", "notice_period": "30 days", "willing_to_relocate": "Yes"}
    page = open_page(window, "questions.html")
    report = fill_step(page, "Application Questions", replace(DETAILS, answers=answers))
    assert [field.value for field in page.fields()] == ["No", "30 days", "Yes", "", ""]
    assert [field.label for field in report.left] == ["Why do you want to work for Acme?"]


def test_disclosures_are_answered_and_the_terms_left_in_the_browser(window):
    page = open_page(window, "disclosures.html")
    report = fill_step(page, "Voluntary Disclosures", replace(DETAILS, answers={"gender": "Female", "ethnicity": "Asian"}))
    assert [field.value for field in page.fields()] == ["Female", "Asian (Not Hispanic or Latino)", "", ""]
    assert [field.kind for field in report.left] == ["select", "checkbox"]
    assert report.left[1].required
