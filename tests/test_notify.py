from datetime import date
from pathlib import Path

from hirejutsu.models import Job, Match
from hirejutsu.notify import picks_message

DAY = date(2026, 10, 17)
REPORT = Path("reports") / "2026-10-17.md"


def match(external_id, score=0.5, **kwargs):
    fields = {"title": f"Python Engineer {external_id}", "company": f"Company {external_id}",
              "url": f"https://x/{external_id}"}
    fields.update(kwargs)
    return Match(Job("demo", external_id, **fields), score)


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
