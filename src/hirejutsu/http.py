"""HTTP client shared by all sources."""

import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__

DEFAULTS = {"timeout": 20, "retries": 2, "user_agent": ""}


class Client:
    """Small wrapper around requests with retries and one session per thread."""

    def __init__(self, timeout: float = 20, retries: int = 2, user_agent: str = ""):
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent or f"hirejutsu/{__version__}"
        self._local = threading.local()

    @classmethod
    def from_settings(cls, settings: dict) -> "Client":
        return cls(timeout=settings["timeout"], retries=settings["retries"], user_agent=settings["user_agent"])

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers["User-Agent"] = self.user_agent
            retry = Retry(
                total=self.retries,
                backoff_factor=1,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=None,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            self._local.session = session
        return session

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        response.raise_for_status()
        return response

    def get_json(self, url: str, params: dict | None = None, headers: dict | None = None):
        return self._send("GET", url, params=params, headers=headers).json()

    def get_text(self, url: str, params: dict | None = None, headers: dict | None = None) -> str:
        return self._send("GET", url, params=params, headers=headers).text

    def post_json(self, url: str, payload, headers: dict | None = None):
        return self._send("POST", url, json=payload, headers=headers).json()

    def post(self, url: str, json=None, data: bytes | None = None, headers: dict | None = None) -> str:
        """POST for services that answer with plain text or nothing at all."""
        return self._send("POST", url, json=json, data=data, headers=headers).text
