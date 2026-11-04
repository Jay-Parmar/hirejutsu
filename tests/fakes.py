"""Test doubles shared by the test suite."""

import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import requests
import yaml

from hirejutsu.config import Config
from hirejutsu.workday import best_option

FIXTURES = Path(__file__).parent / "fixtures"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"


def fixture(name: str):
    """Load a fixture file. JSON files are parsed, anything else is returned as text."""
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else text


def http_error(status: int, url: str = "") -> requests.HTTPError:
    """The error http.Client raises for an HTTP error status."""
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} Client Error for url: {url}", response=response)


def board_config(home: Path, ats: str, boards, **data) -> Config:
    """A config whose only companies are the given boards of one ATS, with any other settings in data."""
    (home / "companies.yaml").write_text(yaml.safe_dump({ats: boards}), encoding="utf-8")
    return Config({"companies": {"builtin": False}, **data}, home)


class FakeClient:
    """Stands in for http.Client and answers from a dict of url to response."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    def _answer(self, method, url, params=None, payload=None):
        self.calls.append((method, url, params, payload))
        if url not in self.routes:
            raise http_error(404, url)
        answer = self.routes[url]
        if isinstance(answer, Exception):
            raise answer
        return answer(params or payload) if callable(answer) else answer

    def get_json(self, url, params=None, headers=None):
        return self._answer("GET", url, params=params)

    def get_text(self, url, params=None, headers=None):
        return self._answer("GET", url, params=params)

    def get_bytes(self, url, params=None, headers=None):
        return self._answer("GET", url, params=params)

    def post_json(self, url, payload, headers=None):
        return self._answer("POST", url, payload=payload)


class FakeRun:
    """Stands in for subprocess.run. Replies, keyed by the first two words, are (code, stdout, stderr) or an error."""

    def __init__(self, replies: dict | None = None):
        self.replies = replies or {}
        self.calls: list[list[str]] = []
        self.inputs: list[str | None] = []
        self.task_file = b""

    def __call__(self, args, input=None, **kwargs):
        self.calls.append(list(args))
        self.inputs.append(input)
        if "/XML" in args:
            self.task_file = Path(args[args.index("/XML") + 1]).read_bytes()
        reply = self.replies.get(" ".join(args[:2]), (0, "", ""))
        if isinstance(reply, Exception):
            raise reply
        return subprocess.CompletedProcess(args, *reply)


class FakePage:
    """Stands in for a Workday tab: holds the fields of a step and records what was filled."""

    def __init__(self, fields=(), entries=None):
        self.items = {item.ref: item for item in fields}
        # The fields of a new entry for each repeating section with an Add button, as {section: fields}.
        self.entries = entries or {}
        self.filled: list[tuple[str, str]] = []

    def fields(self):
        return list(self.items.values())

    def add(self, section: str) -> bool:
        name = next((name for name in self.entries if re.search(section, name, re.IGNORECASE)), None)
        if name is None:
            return False
        number = 1 + max((item.entry for item in self.items.values() if item.section == name), default=0)
        for item in self.entries[name]:
            ref = 1 + max(self.items, default=0)
            self.items[ref] = replace(item, ref=ref, section=name, entry=number)
        return True

    def entry_values(self, section: str) -> dict:
        """{entry: {label: value}} for the entries of a repeating section."""
        found: dict = {}
        for item in self.items.values():
            if item.section == section and item.entry:
                found.setdefault(item.entry, {})[item.label] = item.value
        return found

    def value(self, ref: int) -> str:
        return self.items[ref].value

    def fill(self, field, value: str) -> bool:
        # A field with options only takes one of them, the way the browser picks from a list.
        if field.options:
            index = best_option(value, list(field.options))
            if index is None:
                return False
            value = field.options[index]
        self.items[field.ref] = replace(field, value=value)
        self.filled.append((field.label, value))
        return True


def claude_reply(text: str) -> dict:
    """What the Anthropic Messages API returns for a plain text answer."""
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


def claude_scorer(scores: dict):
    """A FakeClient route that rates the jobs in each prompt from scores, a dict of job id to 0..10."""

    def answer(payload):
        prompt = payload["messages"][0]["content"]
        rated = [
            {"id": job_id, "score": score, "reason": f"Fit {score}"}
            for job_id, score in scores.items()
            if f'<job id="{job_id}">' in prompt
        ]
        return claude_reply(json.dumps(rated))

    return answer
