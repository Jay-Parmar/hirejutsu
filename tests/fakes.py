"""Test doubles shared by the test suite."""

import json
import subprocess
from pathlib import Path

import requests
import yaml

from hirejutsu.config import Config

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
