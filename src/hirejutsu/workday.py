"""Filling Workday application forms from the applicant details.

Everything here works on a small page object, so it runs the same against the browser
(see browser.py) and against the fake page in the tests.
"""

import re


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
