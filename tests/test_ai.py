from pathlib import Path

import pytest
import requests
from fakes import CLAUDE_URL, FakeClient, claude_reply

from hirejutsu import ai
from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


class HeaderClient(FakeClient):
    """FakeClient that also remembers the headers of the last request."""

    def post_json(self, url, payload, headers=None):
        self.headers = headers
        return super().post_json(url, payload, headers)


@pytest.fixture(autouse=True)
def api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def settings(**values):
    return ai.load_settings(Config({"ai": values}, Path(".")))


def test_settings_default_to_anthropic_and_off():
    defaults = settings()
    assert defaults["enabled"] is False
    assert (defaults["provider"], defaults["model"], defaults["base_url"], defaults["api_key_env"]) == (
        "anthropic", "claude-haiku-5-5", "https://api.anthropic.com", "ANTHROPIC_API_KEY",
    )


def test_settings_fill_in_openai_defaults():
    openai = settings(provider="openai")
    assert (openai["model"], openai["base_url"], openai["api_key_env"]) == (
        "gpt-5-mini", "https://api.openai.com/v1", "OPENAI_API_KEY",
    )


def test_settings_keep_values_from_the_config():
    ollama = settings(provider="openai", base_url="http://localhost:11434/v1", model="llama3.1", candidates=12)
    assert (ollama["base_url"], ollama["model"], ollama["candidates"]) == ("http://localhost:11434/v1", "llama3.1", 12)


def test_ai_client_uses_the_ai_timeout():
    assert ai.make_client(settings(timeout=300)).timeout == 300


def test_ask_anthropic_sends_a_messages_request():
    client = HeaderClient({CLAUDE_URL: claude_reply("Hello")})
    assert ai.ask("Be brief.", "Hi", settings(), client) == "Hello"
    assert client.calls[0][3] == {
        "model": "claude-haiku-5-5",
        "max_tokens": 16000,
        "system": "Be brief.",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    assert client.headers == {"x-api-key": "sk-ant-test", "anthropic-version": "2023-06-01"}


def test_ask_anthropic_skips_thinking_blocks():
    reply = {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "OK"}], "stop_reason": "end_turn"}
    assert ai.ask("s", "p", settings(), FakeClient({CLAUDE_URL: reply})) == "OK"


def test_ask_anthropic_needs_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(HirejutsuError, match="ANTHROPIC_API_KEY"):
        ai.ask("s", "p", settings(), FakeClient())


def test_ask_anthropic_reports_a_refusal():
    client = FakeClient({CLAUDE_URL: {"content": [], "stop_reason": "refusal"}})
    with pytest.raises(HirejutsuError, match="declined"):
        ai.ask("s", "p", settings(), client)


def test_ask_openai_sends_a_chat_completion(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    client = HeaderClient({OPENAI_URL: {"choices": [{"message": {"content": "Hello"}}]}})
    assert ai.ask("Be brief.", "Hi", settings(provider="openai"), client) == "Hello"
    assert client.calls[0][3] == {
        "model": "gpt-5-mini",
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}],
    }
    assert client.headers == {"Authorization": "Bearer sk-openai-test"}


def test_ask_local_server_without_a_key():
    url = "http://localhost:11434/v1/chat/completions"
    client = HeaderClient({url: {"choices": [{"message": {"content": "Hi"}}]}})
    ai.ask("s", "p", settings(provider="openai", base_url="http://localhost:11434/v1/", model="llama3.1"), client)
    assert client.calls[0][1] == url
    assert client.headers is None


def test_ask_unknown_provider():
    with pytest.raises(HirejutsuError, match="provider"):
        ai.ask("s", "p", settings(provider="gemini"), FakeClient())


def test_ask_turns_request_errors_into_user_errors():
    with pytest.raises(HirejutsuError, match="no network"):
        ai.ask("s", "p", settings(), FakeClient({CLAUDE_URL: requests.ConnectionError("no network")}))


def test_ask_error_includes_the_api_message():
    response = requests.Response()
    response.status_code = 404
    response._content = b'{"error": {"message": "model: claude-nope not found"}}'
    client = FakeClient({CLAUDE_URL: requests.HTTPError("404 Client Error", response=response)})
    with pytest.raises(HirejutsuError, match="claude-nope not found"):
        ai.ask("s", "p", settings(model="claude-nope"), client)
