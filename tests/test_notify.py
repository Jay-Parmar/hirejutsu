from datetime import date
from pathlib import Path

import pytest
import requests
import yaml

from hirejutsu import notify
from hirejutsu.config import Config, template
from hirejutsu.models import Job, Match
from hirejutsu.notify import Message, picks_message, send_all, split_text

DAY = date(2026, 10, 17)
REPORT = Path("reports") / "2026-10-17.md"
MESSAGE = Message("hirejutsu: test", "hello", "<p>hello</p>")
TELEGRAM = {"enabled": True, "chat_id": 42}
DISCORD_URL = "https://discord.com/api/webhooks/1/abc"
SLACK_URL = "https://hooks.slack.com/services/T1/B1/abc"
GMAIL = {"enabled": True, "host": "smtp.gmail.com", "username": "me@gmail.com", "to": ["me@gmail.com"]}


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


class FakeSMTP:
    """Stands in for an SMTP connection and remembers what it was asked to do."""

    def __init__(self, host, port, secure):
        self.address = (host, port)
        self.secure = secure
        self.steps = []
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.steps.append("quit")

    def starttls(self, context=None):
        self.steps.append("starttls")

    def login(self, username, password):
        self.steps.append(f"login {username} {password}")

    def send_message(self, mail):
        self.steps.append("send")
        self.sent.append(mail)


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


@pytest.fixture
def smtp(monkeypatch):
    """Replace smtplib connections with fakes. Returns the connections that get opened."""
    monkeypatch.setenv("HIREJUTSU_SMTP_PASSWORD", "app-password")
    opened = []

    def opener(secure):
        def connect(host, port, **kwargs):
            opened.append(FakeSMTP(host, port, secure))
            return opened[-1]
        return connect

    monkeypatch.setattr(notify.smtplib, "SMTP", opener(False))
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", opener(True))
    return opened


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


def test_starter_config_lists_every_channel_turned_off(tmp_path, token, webhooks, smtp):
    channels = yaml.safe_load(template())["notify"]
    assert list(channels) == list(notify.SENDERS)
    for name, settings in channels.items():
        assert set(settings) <= set(notify.NOTIFY_DEFAULTS[name]), name
    client = Recorder()
    assert send_all(Config({"notify": channels}, tmp_path), client, MESSAGE) == []
    assert client.posts == [] and smtp == []


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


def test_channel_can_be_switched_with_a_bool_like_sources(tmp_path):
    results = send_all(config(tmp_path, ntfy=True, slack=False), Recorder(), MESSAGE)
    assert results == [("ntfy", "notify.ntfy needs topic in config.yaml")]


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


def test_gmail_uses_starttls_and_the_app_password(tmp_path, smtp):
    assert send_all(config(tmp_path, email=GMAIL), Recorder(), MESSAGE) == [("email", "")]
    [server] = smtp
    assert server.address == ("smtp.gmail.com", 587)
    assert not server.secure
    assert server.steps == ["starttls", "login me@gmail.com app-password", "send", "quit"]
    mail = server.sent[0]
    assert (mail["Subject"], mail["From"], mail["To"]) == ("hirejutsu: test", "me@gmail.com", "me@gmail.com")
    assert mail.get_body(("plain",)).get_content().strip() == "hello"
    assert mail.get_body(("html",)).get_content().strip() == "<p>hello</p>"


def test_email_over_ssl_defaults_to_port_465(tmp_path, smtp):
    send_all(config(tmp_path, email={**GMAIL, "security": "ssl"}), Recorder(), MESSAGE)
    [server] = smtp
    assert server.secure
    assert server.address == ("smtp.gmail.com", 465)
    assert server.steps == ["login me@gmail.com app-password", "send", "quit"]


def test_email_without_username_skips_login(tmp_path, smtp, monkeypatch):
    monkeypatch.delenv("HIREJUTSU_SMTP_PASSWORD")
    settings = {"enabled": True, "host": "localhost", "port": 1025, "security": "none",
                "from": "hirejutsu@localhost", "to": "me@localhost"}
    assert send_all(config(tmp_path, email=settings), Recorder(), MESSAGE) == [("email", "")]
    [server] = smtp
    assert server.address == ("localhost", 1025)
    assert server.steps == ["send", "quit"]
    assert server.sent[0]["To"] == "me@localhost"


def test_email_attaches_reports_only_when_asked(tmp_path, smtp):
    report = tmp_path / "2026-10-17.md"
    report.write_text("# Job picks", encoding="utf-8")
    message = Message("subject", "text", "<p>text</p>", files=[report])
    send_all(config(tmp_path, email=GMAIL), Recorder(), message)
    send_all(config(tmp_path, email={**GMAIL, "attach": True}), Recorder(), message)
    assert list(smtp[0].sent[0].iter_attachments()) == []
    [attachment] = smtp[1].sent[0].iter_attachments()
    assert attachment.get_filename() == "2026-10-17.md"
    assert attachment.get_payload(decode=True) == b"# Job picks"


def test_email_needs_host_sender_and_recipients(tmp_path, smtp):
    assert send_all(config(tmp_path, email={"enabled": True}), Recorder(), MESSAGE) == [
        ("email", "notify.email needs host, from, to in config.yaml"),
    ]
    assert smtp == []


def test_email_rejects_unknown_security(tmp_path, smtp):
    [(name, error)] = send_all(config(tmp_path, email={**GMAIL, "security": "tls"}), Recorder(), MESSAGE)
    assert "starttls, ssl or none" in error
    assert smtp == []


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
