"""Your details for job applications, kept in applicant.yaml in the data folder."""

import json
import re
from dataclasses import dataclass, field, fields
from importlib import resources
from pathlib import Path

import yaml

from .config import Config
from .errors import ConfigError

APPLICANT_NAME = "applicant.yaml"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d \t().-]{8,16}\d")
COUNTRY_CODE = re.compile(r"\+(\d{1,3})[\s.(-]")
LINKEDIN = re.compile(r"linkedin\.com/in/([\w%-]+)", re.IGNORECASE)
GITHUB = re.compile(r"github\.com/([\w-]+)", re.IGNORECASE)
NAME_WORD = re.compile(r"[A-Za-z][A-Za-z.'-]*")
NOT_NAMES = {"resume", "curriculum", "vitae", "cv", "profile", "summary", "contact"}
NEEDED = ("first_name", "last_name", "email", "phone")
KEY_LINE = re.compile(r"(\s*)([a-z_]+):")


@dataclass
class Position:
    title: str
    company: str
    location: str = ""
    start: str = ""
    end: str = ""
    description: str = ""


@dataclass
class School:
    school: str
    degree: str = ""
    field_of_study: str = ""
    start: str = ""
    end: str = ""
    grade: str = ""


@dataclass
class Applicant:
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    phone_code: str = ""
    address: dict = field(default_factory=dict)
    links: dict = field(default_factory=dict)
    work: list = field(default_factory=list)
    education: list = field(default_factory=list)
    answers: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def missing(self) -> list[str]:
        """The basic details every form asks for that are still empty."""
        return [key for key in NEEDED if not getattr(self, key)]


def template() -> str:
    return resources.files("hirejutsu").joinpath("data", APPLICANT_NAME).read_text(encoding="utf-8")


def starter_text(found: dict) -> str:
    """The starter file with the details found in a resume filled in."""
    lines = []
    for line in template().splitlines():
        match = KEY_LINE.match(line)
        if match and found.get(match.group(2)):
            line = f"{match.group(1)}{match.group(2)}: {json.dumps(found[match.group(2)], ensure_ascii=False)}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def applicant_path(config: Config) -> Path:
    return config.path(config.get("applicant", APPLICANT_NAME))


def load_applicant(config: Config) -> Applicant:
    """The details in the applicant file, or none when there is no file yet."""
    path = applicant_path(config)
    if not path.exists():
        return Applicant()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    code = text(data.get("phone_code"))
    return Applicant(
        first_name=text(data.get("first_name")),
        last_name=text(data.get("last_name")),
        email=text(data.get("email")),
        phone=text(data.get("phone")),
        phone_code=f"+{code}" if code and not code.startswith("+") else code,
        address=_mapping(data, "address", path),
        links=_mapping(data, "links", path),
        work=[Position(**entry) for entry in _entries(data, "work", Position, ("title", "company"), path)],
        education=[School(**entry) for entry in _entries(data, "education", School, ("school",), path)],
        answers=_mapping(data, "answers", path),
    )


def found_in_resume(text: str) -> dict:
    """Name, email, phone and profile links in resume text, keyed like applicant.yaml."""
    found = {}
    name = _name(text)
    if name:
        found["first_name"], found["last_name"] = name
    email = EMAIL.search(text)
    if email:
        found["email"] = email.group()
    phone = _phone(text)
    if phone:
        code, found["phone"] = phone
        if code:
            found["phone_code"] = code
    linkedin = LINKEDIN.search(text)
    if linkedin:
        found["linkedin"] = f"https://www.linkedin.com/in/{linkedin.group(1)}"
    github = GITHUB.search(text)
    if github:
        found["github"] = f"https://github.com/{github.group(1)}"
    return found


def _name(text: str) -> tuple[str, str] | None:
    """First and last name from the first line, when that line looks like a name."""
    line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    words = line.split()
    if not 2 <= len(words) <= 4 or not all(NAME_WORD.fullmatch(word) for word in words):
        return None
    if any(word.lower() in NOT_NAMES for word in words):
        return None
    words = [word.capitalize() if word.isupper() else word for word in words]
    return " ".join(words[:-1]), words[-1]


def _phone(text: str) -> tuple[str, str] | None:
    """(country code, number) of the first run of 10 to 13 digits. Shorter runs are dates."""
    for match in PHONE.finditer(text):
        raw = match.group()
        digits = re.sub(r"\D", "", raw)
        if not 10 <= len(digits) <= 13:
            continue
        if not raw.startswith("+"):
            return "", digits
        code = COUNTRY_CODE.match(raw)
        code = code.group(1) if code else digits[:-10]
        return f"+{code}", digits[len(code):]
    return None


def text(value) -> str:
    """A setting as text. YAML reads yes and no as booleans and phone numbers as numbers."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip()


def _mapping(data: dict, key: str, path: Path) -> dict:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' in {path} must be a mapping")
    return {name: text(item) for name, item in value.items() if text(item)}


def _entries(data: dict, key: str, kind: type, required: tuple, path: Path) -> list[dict]:
    """The filled in entries of a list section. The empty entry from the starter file is skipped."""
    value = data.get(key) or []
    if not isinstance(value, list):
        raise ConfigError(f"'{key}' in {path} must be a list")
    known = {item.name for item in fields(kind)}
    entries = []
    for item in value:
        if not isinstance(item, dict):
            raise ConfigError(f"Each entry under '{key}' in {path} must be a mapping")
        entry = {name: text(item_value) for name, item_value in item.items()}
        if not any(entry.values()):
            continue
        unknown = [name for name in entry if name not in known]
        if unknown:
            raise ConfigError(f"Unknown setting '{unknown[0]}' under '{key}' in {path}")
        if not all(entry.get(name) for name in required):
            raise ConfigError(f"Each entry under '{key}' in {path} needs {' and '.join(required)}")
        entries.append(entry)
    return entries
