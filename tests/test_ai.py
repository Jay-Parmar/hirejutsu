import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
import yaml
from fakes import CLAUDE_URL, FakeClient, claude_reply, claude_scorer

from hirejutsu import ai
from hirejutsu.config import Config, template
from hirejutsu.errors import HirejutsuError
from hirejutsu.models import Job, Match, Profile
from hirejutsu.store import Store

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
PROFILE = Profile(text="Python developer with five years of Django")


class HeaderClient(FakeClient):
    """FakeClient that also remembers the headers of the last request."""

    def post_json(self, url, payload, headers=None):
        self.headers = headers
        return super().post_json(url, payload, headers)


@pytest.fixture(autouse=True)
def api_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as store:
        yield store


def settings(**values):
    return ai.load_settings(Config({"ai": values}, Path(".")))


def saved_matches(store, *scores):
    """One saved job per heuristic score, returned as matches."""
    jobs = [Job("demo", str(n), f"Engineer {n}", f"Company {n}", f"https://x/{n}", description="D" * 50)
            for n in range(len(scores))]
    store.upsert_jobs(jobs, NOW)
    return [Match(job, score, ["Skills: python"]) for job, score in zip(store.find_jobs(), scores)]


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


def test_starter_config_has_the_ai_section_off():
    section = yaml.safe_load(template())["ai"]
    assert section == {key: ai.AI_DEFAULTS[key] for key in section}
    assert section["enabled"] is False


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


def test_explain_asks_about_one_job_and_returns_the_answer():
    job = Job("demo", "1", "Data Engineer", "Acme", "https://x/1", location="Pune", remote=True, description="Spark", id=7)
    client = FakeClient({CLAUDE_URL: claude_reply("  7/10. Spark fits, Airflow is missing.  ")})
    assert ai.explain(job, PROFILE, settings(), client) == "7/10. Spark fits, Airflow is missing."
    prompt = client.calls[0][3]["messages"][0]["content"]
    assert PROFILE.text in prompt
    assert '<job id="7">' in prompt and "Location: Pune" in prompt and "Remote: yes" in prompt


def test_parse_scores_reads_a_json_list():
    reply = '[{"id": 1, "score": 8, "reason": "Python fits"}, {"id": 2, "score": 3.5, "reason": "Needs Go"}]'
    assert ai.parse_scores(reply, {1, 2}) == {1: (8.0, "Python fits"), 2: (3.5, "Needs Go")}


def test_parse_scores_ignores_code_fences_and_chatter():
    reply = 'Scores for jobs [1]:\n```json\n[{"id": 1, "score": 7, "reason": "Good"}]\n```\nHope this helps!'
    assert ai.parse_scores(reply, {1}) == {1: (7.0, "Good")}


def test_parse_scores_accepts_a_wrapped_list_and_strings():
    reply = '{"jobs": [{"id": "1", "score": "6", "reason": "Fine"}]}'
    assert ai.parse_scores(reply, {1}) == {1: (6.0, "Fine")}


def test_parse_scores_skips_bad_entries():
    reply = json.dumps([
        {"id": 1, "score": 11},
        {"id": 2},
        {"id": 99, "score": 5},
        {"id": "x", "score": 5},
        "junk",
        {"id": 3, "score": 4, "reason": "Two\nlines"},
        {"id": 4, "score": 0},
    ])
    assert ai.parse_scores(reply, {1, 2, 3, 4}) == {3: (4.0, "Two lines"), 4: (0.0, "")}


def test_parse_scores_without_usable_json():
    assert ai.parse_scores("Sorry, I can't help with that.", {1}) == {}
    assert ai.parse_scores('[{"id": 1, "score": 5', {1}) == {}


def test_rerank_blends_ai_scores_and_reorders(store):
    first, second = saved_matches(store, 0.8, 0.4)
    client = FakeClient({CLAUDE_URL: claude_scorer({first.job.id: 2, second.job.id: 10})})
    assert ai.rerank([first, second], PROFILE, settings(), store, client) == [
        Match(second.job, 0.7, ["AI: Fit 10", "Skills: python"]),
        Match(first.job, 0.5, ["AI: Fit 2", "Skills: python"]),
    ]


def test_rerank_sends_the_resume_and_jobs_in_batches(store):
    matches = saved_matches(store, 0.9, 0.8, 0.7)
    client = FakeClient({CLAUDE_URL: claude_scorer({match.job.id: 5 for match in matches})})
    limits = settings(batch_size=2, max_resume_chars=10, max_description_chars=20)
    ai.rerank(matches, Profile(text="R" * 50), limits, store, client)
    prompts = [payload["messages"][0]["content"] for *_, payload in client.calls]
    assert len(prompts) == 2
    assert "Engineer 0" in prompts[0] and "Engineer 1" in prompts[0] and "Engineer 2" in prompts[1]
    assert "R" * 10 in prompts[0] and "R" * 11 not in prompts[0]
    assert "D" * 20 in prompts[0] and "D" * 21 not in prompts[0]


def test_rerank_reuses_cached_scores(store):
    matches = saved_matches(store, 0.5)
    ai.rerank(matches, PROFILE, settings(), store, FakeClient({CLAUDE_URL: claude_scorer({matches[0].job.id: 8})}))
    offline = FakeClient()
    assert ai.rerank(matches, PROFILE, settings(), store, offline)[0].reasons[0] == "AI: Fit 8"
    assert offline.calls == []


def test_rerank_asks_again_for_a_new_resume_or_model(store):
    matches = saved_matches(store, 0.5)
    client = FakeClient({CLAUDE_URL: claude_scorer({matches[0].job.id: 8})})
    ai.rerank(matches, PROFILE, settings(), store, client)
    ai.rerank(matches, Profile(text="Go developer"), settings(), store, client)
    ai.rerank(matches, PROFILE, settings(model="claude-sonnet-5-5"), store, client)
    assert len(client.calls) == 3


def test_rerank_keeps_usual_scores_when_requests_fail(store, caplog):
    matches = saved_matches(store, 0.9, 0.5)
    client = FakeClient({CLAUDE_URL: requests.ConnectionError("no network")})
    assert ai.rerank(matches, PROFILE, settings(batch_size=1), store, client) == matches
    assert len(client.calls) == 2
    assert "no network" in caplog.text


def test_rerank_survives_an_unexpected_answer(store, caplog):
    matches = saved_matches(store, 0.9)
    client = FakeClient({CLAUDE_URL: {"surprise": True}})
    assert ai.rerank(matches, PROFILE, settings(), store, client) == matches
    assert "AI scoring failed" in caplog.text


def test_rerank_keeps_usual_scores_for_jobs_the_ai_skipped(store, caplog):
    first, second = saved_matches(store, 0.9, 0.5)
    client = FakeClient({CLAUDE_URL: claude_scorer({second.job.id: 10})})
    assert ai.rerank([first, second], PROFILE, settings(), store, client) == [
        first,
        Match(second.job, 0.75, ["AI: Fit 10", "Skills: python"]),
    ]
    assert "1 of 2" in caplog.text
