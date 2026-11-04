"""Filling Workday application forms from the applicant details.

Everything here works on a small page object, so it runs the same against the browser
(see browser.py) and against the fake page in the tests.
"""

import re
from dataclasses import dataclass, field

from .applicant import Applicant

# The steps hirejutsu knows, found in the progress bar label or, on older pages, the step's data-automation-id.
STEPS = {
    "My Information": r"my ?information|contact ?information|myinfo",
    "My Experience": r"my ?experience|myexp",
    "Application Questions": r"question",
    "Voluntary Disclosures": r"voluntary ?disclosure",
    "Self Identify": r"self.?identif",
    "Review": r"review",
}
STEP_NUMBER = re.compile(r"(current )?step \d+ of \d+", re.IGNORECASE)


@dataclass
class Field:
    """One field of a form, as the page reads it."""

    ref: int
    # The data-automation-id of the field's box, without "formField-", and those of its controls.
    ids: tuple = ()
    label: str = ""
    # text, textarea, select, prompt, radio, checkbox, checkboxes, date, file or other.
    kind: str = "text"
    # What it holds now. Empty when nothing is filled in.
    value: str = ""
    required: bool = False
    # The heading of the section it is in, and its entry there when the section repeats, from 1.
    section: str = ""
    entry: int = 0
    # The labels of its radio buttons or check boxes.
    options: tuple = ()


@dataclass
class Want:
    """A value and the field it goes in: one with any of these ids, or else one whose label starts with label."""

    value: str
    ids: tuple
    label: str = ""
    section: str = ""
    entry: int = 0


@dataclass
class Report:
    """What hirejutsu filled on one step, and the empty fields it left for you."""

    step: str
    filled: list = field(default_factory=list)
    left: list = field(default_factory=list)


def step_name(text: str) -> str:
    """The name of the step a progress bar label shows. Steps hirejutsu does not know keep their label."""
    for name, pattern in STEPS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return STEP_NUMBER.sub("", text).strip()


def find(fields: list[Field], want: Want) -> Field | None:
    """The field a value goes in, found by data-automation-id first and by its label after that."""
    here = [item for item in fields if item.entry == want.entry and re.search(want.section, item.section, re.IGNORECASE)]
    by_id = next((item for item in here if set(item.ids) & set(want.ids)), None)
    if by_id or not want.label:
        return by_id
    return next((item for item in here if re.match(want.label, item.label, re.IGNORECASE)), None)


def words(text: str) -> str:
    """Text in lower case without punctuation, for comparing an answer with the options."""
    return " ".join(re.sub(r"[^\w\s/]", "", text.lower()).replace("/", " ").split())


def best_option(answer: str, options: list[str]) -> int | None:
    """The index of the option that is the answer, or else the first one that starts with it."""
    wanted = words(answer)
    if not wanted:
        return None
    found = [words(option) for option in options]
    if wanted in found:
        return found.index(wanted)
    return next((index for index, option in enumerate(found) if option.startswith(wanted + " ")), None)


def fill_step(page, step: str, details: Applicant) -> Report:
    """Fill the empty fields hirejutsu knows on one step of the application."""
    report = Report(step)
    if step == "My Information":
        fill_values(page, information(details), report)
    report.left = [item for item in page.fields() if not item.value]
    return report


def fill_values(page, wants: list[Want], report: Report) -> None:
    """Put each value in its field, when the field is on the page and still empty."""
    for want in wants:
        if not want.value:
            continue
        found = find(page.fields(), want)
        if found and not found.value and page.fill(found, want.value):
            report.filled.append((found.label, want.value))


def information(details: Applicant) -> list[Want]:
    """Where the details go on the My Information step."""
    address, answers = details.address, details.answers
    country = address.get("country", "")
    phone_code = f"{country} ({details.phone_code})" if country and details.phone_code else ""
    return [
        Want(answers.get("how_did_you_hear", ""), ("source", "sourcePrompt"), r"how did you hear"),
        # Most people apply to companies they never worked for, so this one is answered unless told otherwise.
        Want(
            answers.get("worked_here_before", "No"),
            ("candidateIsPreviousWorker", "previousWorker"),
            r"have you (previously|ever) (worked|been employed)",
        ),
        Want(country, ("country",), r"country( ?/ ?region)?$"),
        Want(details.first_name, ("legalName--firstName", "legalNameSection_firstName"), r"(first|given) name"),
        Want(details.last_name, ("legalName--lastName", "legalNameSection_lastName"), r"(last|family) name"),
        Want(address.get("line1", ""), ("addressLine1", "addressSection_addressLine1"), r"address line 1"),
        Want(address.get("city", ""), ("city", "addressSection_city"), r"city"),
        Want(address.get("state", ""), ("countryRegion", "addressSection_countryRegion"), r"state|province|region"),
        Want(address.get("postal_code", ""), ("postalCode", "addressSection_postalCode"), r"postal code|zip|pin ?code"),
        Want(details.email, ("email",), r"email"),
        Want("Mobile" if details.phone else "", ("phoneType", "phone-device-type"), r"phone device type"),
        Want(phone_code, ("countryPhoneCode", "country-phone-code"), r"country phone code"),
        Want(details.phone, ("phoneNumber", "phone-number"), r"phone number"),
    ]
