"""Filling Workday application forms from the applicant details.

Everything here works on a small page object, so it runs the same against the browser
(see browser.py) and against the fake page in the tests.
"""

import re

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


def step_name(text: str) -> str:
    """The name of the step a progress bar label shows. Steps hirejutsu does not know keep their label."""
    for name, pattern in STEPS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return STEP_NUMBER.sub("", text).strip()


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
