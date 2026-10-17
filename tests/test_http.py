import json
import threading

import pytest
import requests

from hirejutsu import __version__
from hirejutsu.http import Client


class StubAdapter(requests.adapters.BaseAdapter):
    def __init__(self, status=200, body=b'{"ok": true}'):
        super().__init__()
        self.status = status
        self.body = body
        self.sent = []

    def send(self, request, **kwargs):
        self.sent.append(request)
        response = requests.Response()
        response.status_code = self.status
        response._content = self.body
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass


def stub(client, **kwargs):
    adapter = StubAdapter(**kwargs)
    client.session.mount("https://", adapter)
    return adapter


def test_default_user_agent_names_the_app():
    assert Client().session.headers["User-Agent"] == f"hirejutsu/{__version__}"


def test_custom_user_agent():
    assert Client(user_agent="me").session.headers["User-Agent"] == "me"


def test_one_session_per_thread():
    client = Client()
    seen = []
    thread = threading.Thread(target=lambda: seen.append(client.session))
    thread.start()
    thread.join()
    assert client.session is client.session
    assert seen[0] is not client.session


def test_get_json_sends_params():
    client = Client()
    adapter = stub(client)
    assert client.get_json("https://example.com/jobs", params={"q": "python dev"}) == {"ok": True}
    assert adapter.sent[0].url == "https://example.com/jobs?q=python+dev"


def test_get_json_raises_on_error_status():
    client = Client()
    stub(client, status=404, body=b"missing")
    with pytest.raises(requests.HTTPError):
        client.get_json("https://example.com/jobs")


def test_get_text():
    client = Client()
    stub(client, body=b"<rss/>")
    assert client.get_text("https://example.com/feed") == "<rss/>"


def test_post_json_sends_payload():
    client = Client()
    adapter = stub(client)
    client.post_json("https://example.com/search", {"limit": 20})
    assert json.loads(adapter.sent[0].body) == {"limit": 20}
    assert adapter.sent[0].method == "POST"
