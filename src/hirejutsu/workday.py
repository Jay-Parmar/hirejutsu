"""Filling Workday application forms from the applicant details.

Everything here works on a small page object, so it runs the same against the browser
(see browser.py) and against the fake page in the tests.
"""

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .applicant import Applicant, Position, School

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
# Headings of the repeating sections on My Experience. Some companies say Professional Experience.
WORK = r"experience|employment"
EDUCATION = r"education"
WEBSITES = r"website|portfolio"
RESUME = r"resume|cv"
# Workday reads these resumes. Other files are left for you to upload.
UPLOADS = (".pdf", ".docx")
# What an application question has to say to get one of your answers.
QUESTIONS = {
    "notice_period": r"notice period|how soon can you (start|join)|earliest (start|joining) date|available to (start|join)",
    "expected_salary": r"expected\b.{0,30}\b(salary|ctc|compensation|pay)|salary expectation|desired (salary|pay)",
    "current_salary": r"current\b.{0,30}\b(salary|ctc|compensation|pay)",
    "authorized_to_work": r"(authori[sz]ed|eligible|permitted|right) to work|work (permit|authori[sz]ation)",
    "needs_sponsorship": r"sponsor",
    "willing_to_relocate": r"relocat",
    "how_did_you_hear": r"how did you (hear|learn|find)|where did you (hear|see|find)",
}
# Fields a question can be answered in. Dates, files and check boxes are left for you.
ANSWERABLE = ("text", "textarea", "select", "prompt", "radio")
# Voluntary disclosures: the ids of each question, and what its label or its choices mention.
DISCLOSURES = {
    "gender": (("gender",), r"gender"),
    "ethnicity": (("ethnicity", "ethnicityDropdown", "race"), r"ethnic|race"),
    "veteran_status": (("veteranStatus", "veteran"), r"veteran"),
    "disability": (("disability", "disabilityStatus"), r"disabilit"),
}
# Fields that ask you to agree to something. Those are always left for you.
CONSENT = r"consent|agree|terms|acknowledg|privacy|certify|attest|signature"


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


def fillable(item: Field) -> bool:
    """True for an empty field that does not ask you to agree to something."""
    return not item.value and not re.search(CONSENT, item.label, re.IGNORECASE)


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


def fill_step(page, step: str, details: Applicant, skills: list[str] = (), resume: Path | None = None) -> Report:
    """Fill the empty fields hirejutsu knows on one step of the application."""
    report = Report(step)
    if step == "My Information":
        fill_values(page, information(details), report)
    elif step == "My Experience":
        fill_experience(page, details, skills, resume, report)
    elif step == "Application Questions":
        fill_questions(page, details.answers, report)
    elif step in ("Voluntary Disclosures", "Self Identify"):
        fill_disclosures(page, details.answers, report)
    report.left = [item for item in page.fields() if not item.value]
    return report


def fill_experience(page, details: Applicant, skills: list[str], resume: Path | None, report: Report) -> None:
    """Jobs, schools, skills, the resume and links on the My Experience step."""
    fill_entries(page, WORK, [job(position) for position in details.work], report)
    fill_entries(page, EDUCATION, [education(school) for school in details.education], report)
    fill_skills(page, skills, report)
    upload = str(resume) if resume and resume.suffix.lower() in UPLOADS else ""
    fill_values(page, [Want(upload, ("file-upload-input-ref",), r"upload|resume|cv", RESUME)], report)
    fill_links(page, details.links, report)


def fill_values(page, wants: list[Want], report: Report) -> None:
    """Put each value in its field, when the field is on the page and still empty."""
    for want in wants:
        if not want.value:
            continue
        found = find(page.fields(), want)
        if found and fillable(found) and page.fill(found, want.value):
            report.filled.append((found.label, want.value))


def fill_skills(page, skills: list[str], report: Report) -> None:
    """Pick each skill in the skills box, when the box is still empty."""
    want = Want("skills", ("skills", "skillsPrompt"), r"(type to add )?skills")
    found = find(page.fields(), want)
    if not found or not fillable(found):
        return
    added = []
    for skill in skills:
        # Looked up again for each skill, as the box changes with every pick.
        found = find(page.fields(), want)
        if found and page.fill(found, skill):
            added.append(skill)
    if added:
        report.filled.append((found.label, ", ".join(added)))


def fill_links(page, links: dict, report: Report) -> None:
    """LinkedIn goes in its own box when there is one. The other links become websites."""
    linkedin = Want(links.get("linkedin", ""), ("linkedInAccount", "linkedinQuestion"), r"linkedin")
    has_box = find(page.fields(), linkedin) is not None
    fill_values(page, [linkedin], report)
    urls = [url for name, url in links.items() if not (has_box and name == "linkedin")]
    fill_entries(page, WEBSITES, [[Want(url, ("url", "website"), r"url|website|link")] for url in urls], report)


def fill_questions(page, answers: dict, report: Report) -> None:
    """Answer each question whose text asks for one of your answers."""
    for question in page.fields():
        key = answer_key(question.label)
        if key and question.kind in ANSWERABLE:
            fill_values(page, [Want(answers.get(key, ""), question.ids, re.escape(question.label))], report)


def fill_disclosures(page, answers: dict, report: Report) -> None:
    """Answer the voluntary disclosures you gave answers for. The others are left for you."""
    for key, (ids, pattern) in DISCLOSURES.items():
        answer = answers.get(key, "")
        if not answer:
            continue
        fields = page.fields()
        found = find(fields, Want(answer, ids)) or mentioning(fields, pattern)
        if found and fillable(found) and found.kind in (*ANSWERABLE, "checkboxes") and page.fill(found, answer):
            report.filled.append((found.label, answer))


def mentioning(fields: list[Field], pattern: str) -> Field | None:
    """The first field whose label or choices mention pattern. The disability form only names its choices."""
    return next((item for item in fields if re.search(pattern, " ".join([item.label, *item.options]), re.IGNORECASE)), None)


def answer_key(question: str) -> str | None:
    """The answer a question asks for. A question that fits two, like working without sponsorship, is left for you."""
    keys = [key for key, pattern in QUESTIONS.items() if re.search(pattern, question, re.IGNORECASE)]
    return keys[0] if len(keys) == 1 else None


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


def fill_entries(page, section: str, rows: list[list[Want]], report: Report) -> None:
    """Fill an entry of a repeating section for each row of values, adding entries as needed.

    The first value of a row tells entries apart. An entry that already holds it, like one Workday
    filled in from the resume, is completed instead of getting a second entry.
    """
    used: set[int] = set()
    for row in rows:
        entries = entries_of(page.fields(), section)
        number = holding(entries, row[0], used) or empty_entry(entries, used) or added_entry(page, section, entries)
        if not number:
            return
        used.add(number)
        fill_values(page, [replace(want, section=section, entry=number) for want in row], report)


def entries_of(fields: list[Field], section: str) -> dict[int, list[Field]]:
    """The fields of each entry of a repeating section, by entry number."""
    found: dict[int, list[Field]] = {}
    for item in fields:
        if item.entry and re.search(section, item.section, re.IGNORECASE):
            found.setdefault(item.entry, []).append(item)
    return found


def holding(entries: dict[int, list[Field]], want: Want, used: set[int]) -> int | None:
    """The entry that already holds what want says, like the same company."""
    for number, items in entries.items():
        found = find(items, replace(want, entry=number))
        if number not in used and found and same(found.value, want.value):
            return number
    return None


def empty_entry(entries: dict[int, list[Field]], used: set[int]) -> int | None:
    """The first entry with nothing filled in."""
    for number, items in sorted(entries.items()):
        if number not in used and not any(item.value for item in items):
            return number
    return None


def added_entry(page, section: str, entries: dict[int, list[Field]]) -> int | None:
    """The number of a new entry after clicking the section's Add button."""
    if not page.add(section):
        return None
    number = max(entries_of(page.fields(), section), default=None)
    return None if number in entries else number


def same(first: str, second: str) -> bool:
    """True when one text has every word of the other, as Acme and Acme Inc do."""
    one, other = set(words(first).split()), set(words(second).split())
    return bool(one and other) and (one <= other or other <= one)


def job(position: Position) -> list[Want]:
    """Where one job goes in a Work Experience entry. The company comes first, as it tells jobs apart."""
    return [
        Want(position.company, ("companyName", "company"), r"company"),
        Want(position.title, ("jobTitle",), r"job title"),
        Want(position.location, ("location",), r"location"),
        Want("" if position.end else "Yes", ("currentlyWorkHere",), r"i currently work here"),
        Want(month_year(position.start), ("startDate",), r"from$"),
        Want(month_year(position.end), ("endDate",), r"to$"),
        Want(position.description, ("roleDescription", "description"), r"role description"),
    ]


def education(school: School) -> list[Want]:
    """Where one school goes in an Education entry. The school comes first, as it tells schools apart."""
    return [
        Want(school.school, ("schoolName", "schoolItem", "school"), r"school"),
        Want(school.degree, ("degree",), r"degree"),
        Want(school.field_of_study, ("fieldOfStudy", "field-of-study"), r"field of study"),
        Want(school.grade, ("gradeAverage", "gpa"), r"overall result|grade|gpa"),
        Want(month_year(school.start), ("firstYearAttended", "startDate"), r"from$|first year"),
        Want(month_year(school.end), ("lastYearAttended", "endDate"), r"to$|last year"),
    ]


def month_year(value: str) -> str:
    """A YYYY-MM or YYYY date as Workday writes it, MM/YYYY or YYYY. Other dates are left out."""
    found = re.fullmatch(r"(\d{4})(?:-(\d{1,2}))?", value.strip())
    if not found:
        return ""
    year, month = found.groups()
    return f"{int(month):02d}/{year}" if month else year
