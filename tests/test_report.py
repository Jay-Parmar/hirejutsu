from datetime import date

from hirejutsu.config import Config
from hirejutsu.models import Job, Match
from hirejutsu.report import markdown, write_reports


def job(external_id, **kwargs):
    fields = {"title": f"Python Engineer {external_id}", "company": external_id, "url": f"https://x/{external_id}"}
    fields.update(kwargs)
    return Job("demo", external_id, **fields)


def test_markdown_lists_jobs_with_links():
    text = markdown([Match(job("a", id=7, location="Remote"), 0.75, ["Skills: python"])], date(2026, 10, 17))
    assert "# Job picks for 2026-10-17" in text
    assert "## 1. Python Engineer a at a" in text
    assert "- Skills: python" in text
    assert "https://x/a" in text
    assert "id 7" in text


def test_write_reports_saves_markdown(tmp_path):
    paths = write_reports([Match(job("a", id=1), 0.5)], Config({}, tmp_path), date(2026, 10, 17))
    assert paths == [tmp_path / "reports" / "2026-10-17.md"]
    assert "Python Engineer a" in paths[0].read_text(encoding="utf-8")
