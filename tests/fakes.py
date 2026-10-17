"""Test doubles shared by the test suite."""

import json
from pathlib import Path

import requests

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    """Load a fixture file. JSON files are parsed, anything else is returned as text."""
    path = FIXTURES / name
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else text


class FakeClient:
    """Stands in for http.Client and answers from a dict of url to response."""

    def __init__(self, routes: dict | None = None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    def _answer(self, method, url, params=None, payload=None):
        self.calls.append((method, url, params, payload))
        if url not in self.routes:
            raise requests.HTTPError(f"404 Not Found: {url}")
        answer = self.routes[url]
        if isinstance(answer, Exception):
            raise answer
        return answer(params or payload) if callable(answer) else answer

    def get_json(self, url, params=None, headers=None):
        return self._answer("GET", url, params=params)

    def get_text(self, url, params=None, headers=None):
        return self._answer("GET", url, params=params)

    def post_json(self, url, payload, headers=None):
        return self._answer("POST", url, payload=payload)
