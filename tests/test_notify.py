from datetime import date
from pathlib import Path

import pytest
import requests

from hirejutsu.config import Config
from hirejutsu.models import Job, Match
from hirejutsu.notify import Message, picks_message, send_all, split_text

DAY = date(2026, 10, 17)
REPORT = Path("reports") / "2026-10-17.md"
MESSAGE = Message("hirejutsu: test", "hello", "<p>hello</p>")
TELEGRAM = {"enabled": True, "chat_id": 42}
DISCORD_URL = "https://discord.com/api/webhooks/1/abc"
SLACK_URL = "https://hooks.slack.com/services/T1/B1/abc"


class Recorder:
    """Stands in for http.Client and keeps every POST instead of sending it."""

    def __init__(self, error=None):
        self.posts = []
        self.error = error

    def post(self, url, json=None, data=None, headers=None):
        self.posts.append({"url": url, "json": json, "data": data, "headers": headers or {}})
        if self.error:
            raise self.error
        return ""


def match(external_id, score=0.5, **kwargs):
    fields = {"title": f"Python Engineer {external_id}", "company": f"Company {external_id}",
              "url": f"https://x/{external_id}"}
    fields.update(kwargs)
    return Match(Job("demo", external_id, **fields), score)


def config(tmp_path, **channels):
    return Config({"notify": channels}, tmp_path)


def http_error(status, body, url):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.url = url
    return requests.HTTPError(f"{status} Client Error: for url: {url}", response=response)


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("HIREJUTSU_TELEGRAM_TOKEN", "123:secret")


@pytest.fixture
def webhooks(monkeypatch):
    monkeypatch.setenv("HIREJUTSU_DISCORD_WEBHOOK", DISCORD_URL)
    monkeypatch.setenv("HIREJUTSU_SLACK_WEBHOOK", SLACK_URL)


def test_picks_message_lists_jobs_and_report():
    message = picks_message([match("a", 0.75, location="Pune"), match("b", remote=True)], DAY, [REPORT])
    assert message.subject == "hirejutsu: 2 picks for 2026-10-17"
    assert "1. Python Engineer a at Company a\n   Pune | score 0.75\n   https://x/a" in message.text
    assert "2. Python Engineer b at Company b\n   Remote | score 0.50\n   https://x/b" in message.text
    assert message.text.endswith(f"Report: {REPORT}")
    assert message.link == "https://x/a"
    assert message.files == [REPORT]


def test_picks_message_html_is_escaped_and_self_contained():
    message = picks_message([match("a", title="R&D <Lead>")], DAY, [REPORT])
    assert '<a href="https://x/a"' in message.html
    assert "R&amp;D &lt;Lead&gt;" in message.html
    assert str(REPORT) in message.html
    assert "<img" not in message.html and "<style" not in message.html


def test_split_text_keeps_paragraphs_together():
    assert split_text("aa\n\nbb\n\ncc", 6) == ["aa\n\nbb", "cc"]
    assert split_text("abcdefg", 3) == ["abc", "def", "g"]


def test_nothing_is_sent_by_default(tmp_path, token):
    client = Recorder()
    assert send_all(Config({}, tmp_path), client, MESSAGE) == []
    assert client.posts == []


def test_telegram_sends_plain_text(tmp_path, token):
    client = Recorder()
    assert send_all(config(tmp_path, telegram=TELEGRAM), client, MESSAGE) == [("telegram", "")]
    [post] = client.posts
    assert post["url"] == "https://api.telegram.org/bot123:secret/sendMessage"
    assert post["json"]["chat_id"] == 42
    assert post["json"]["text"] == "hirejutsu: test\n\nhello"
    assert "parse_mode" not in post["json"]


def test_telegram_splits_long_messages(tmp_path, token):
    client = Recorder()
    long = Message("subject", "\n\n".join("x" * 1000 for _ in range(9)), "")
    send_all(config(tmp_path, telegram=TELEGRAM), client, long)
    texts = [post["json"]["text"] for post in client.posts]
    assert len(texts) == 3
    assert all(len(text) <= 4096 for text in texts)
    assert "".join(texts).count("x") == 9000


def test_missing_settings_are_reported(tmp_path, token):
    results = send_all(config(tmp_path, telegram={"enabled": True}), Recorder(), MESSAGE)
    assert results == [("telegram", "notify.telegram needs chat_id in config.yaml")]


def test_missing_env_var_is_named(tmp_path, monkeypatch):
    monkeypatch.delenv("HIREJUTSU_TELEGRAM_TOKEN", raising=False)
    [(name, error)] = send_all(config(tmp_path, telegram=TELEGRAM), Recorder(), MESSAGE)
    assert "HIREJUTSU_TELEGRAM_TOKEN is not set" in error


def test_secret_written_in_config_works_with_a_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("HIREJUTSU_TELEGRAM_TOKEN", raising=False)
    client = Recorder()
    send_all(config(tmp_path, telegram={**TELEGRAM, "bot_token": "9:literal"}), client, MESSAGE)
    assert client.posts[0]["url"] == "https://api.telegram.org/bot9:literal/sendMessage"
    assert "bot_token_env" in caplog.text


def test_http_error_shows_status_and_reply_but_not_the_token(tmp_path, token):
    error = http_error(400, b'{"description": "Bad Request: chat not found"}',
                       "https://api.telegram.org/bot123:secret/sendMessage")
    [(name, reason)] = send_all(config(tmp_path, telegram=TELEGRAM), Recorder(error), MESSAGE)
    assert "400" in reason and "chat not found" in reason
    assert "secret" not in reason


def test_connection_error_does_not_show_the_token(tmp_path, token):
    error = requests.ConnectionError("Max retries exceeded with url: /bot123:secret/sendMessage")
    [(name, reason)] = send_all(config(tmp_path, telegram=TELEGRAM), Recorder(error), MESSAGE)
    assert "ConnectionError" in reason
    assert "secret" not in reason


def test_discord_posts_content_without_link_previews(tmp_path, webhooks):
    client = Recorder()
    assert send_all(config(tmp_path, discord={"enabled": True}), client, MESSAGE) == [("discord", "")]
    [post] = client.posts
    assert post["url"] == DISCORD_URL
    assert post["json"] == {"content": "hirejutsu: test\n\nhello", "flags": 4}


def test_discord_splits_at_2000_characters(tmp_path, webhooks):
    client = Recorder()
    long = Message("subject", "\n\n".join("x" * 500 for _ in range(9)), "")
    send_all(config(tmp_path, discord={"enabled": True}), client, long)
    assert len(client.posts) == 3
    assert all(len(post["json"]["content"]) <= 2000 for post in client.posts)


def test_slack_escapes_markup_characters(tmp_path, webhooks):
    client = Recorder()
    message = Message("hirejutsu: test", "R&D <Lead>", "")
    assert send_all(config(tmp_path, slack={"enabled": True}), client, message) == [("slack", "")]
    [post] = client.posts
    assert post["url"] == SLACK_URL
    assert post["json"] == {"text": "hirejutsu: test\n\nR&amp;D &lt;Lead&gt;"}


def test_webhook_url_written_in_config_works(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("HIREJUTSU_SLACK_WEBHOOK", raising=False)
    client = Recorder()
    send_all(config(tmp_path, slack={"enabled": True, "webhook_url": SLACK_URL}), client, MESSAGE)
    assert client.posts[0]["url"] == SLACK_URL
    assert "webhook_url_env" in caplog.text


def test_ntfy_posts_plain_text_with_title_and_click(tmp_path):
    client = Recorder()
    message = Message("hirejutsu: 2 picks for 2026-10-17", "1. Caf\u00e9 owner", "", link="https://x/a")
    assert send_all(config(tmp_path, ntfy={"enabled": True, "topic": "my-picks"}), client, message) == [("ntfy", "")]
    [post] = client.posts
    assert post["url"] == "https://ntfy.sh/my-picks"
    assert post["data"] == b"1. Caf\xc3\xa9 owner"
    assert post["headers"] == {"Title": "hirejutsu: 2 picks for 2026-10-17", "Click": "https://x/a"}


def test_ntfy_uses_own_server_and_token(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_NTFY_TOKEN", "tk_abc")
    client = Recorder()
    settings = {"enabled": True, "server": "https://ntfy.example.com/", "topic": "jobs", "token_env": "MY_NTFY_TOKEN"}
    send_all(config(tmp_path, ntfy=settings), client, MESSAGE)
    [post] = client.posts
    assert post["url"] == "https://ntfy.example.com/jobs"
    assert post["headers"]["Authorization"] == "Bearer tk_abc"
    assert "Click" not in post["headers"]


def test_ntfy_needs_a_topic(tmp_path):
    results = send_all(config(tmp_path, ntfy={"enabled": True}), Recorder(), MESSAGE)
    assert results == [("ntfy", "notify.ntfy needs topic in config.yaml")]


def test_a_failing_channel_does_not_stop_the_others(tmp_path, webhooks):
    client = Recorder()
    channels = {"telegram": {"enabled": True}, "discord": {"enabled": True}, "slack": {"enabled": True}}
    results = send_all(config(tmp_path, **channels), client, MESSAGE)
    assert [(name, bool(error)) for name, error in results] == [("telegram", True), ("discord", False), ("slack", False)]
    assert [post["url"] for post in client.posts] == [DISCORD_URL, SLACK_URL]


def test_only_sends_to_the_named_channel(tmp_path, token, webhooks):
    client = Recorder()
    channels = {"telegram": TELEGRAM, "discord": {"enabled": True}}
    assert send_all(config(tmp_path, **channels), client, MESSAGE, only="discord") == [("discord", "")]
    assert send_all(config(tmp_path, **channels), client, MESSAGE, only="slack") == []
