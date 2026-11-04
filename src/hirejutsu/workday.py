"""Filling Workday application forms from the applicant details.

Everything here works on a small page object, so it runs the same against the browser
(see browser.py) and against the fake page in the tests.
"""

import re
from dataclasses import dataclass

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
