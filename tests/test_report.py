import codecs
import csv
import io
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from rich.console import Console

from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.models import Job, Match
from hirejutsu.report import age, html_page, markdown, print_picks, salary, write_reports

DAY = date(2026, 10, 17)


def job(external_id, **kwargs):
    fields = {"title": f"Python Engineer {external_id}", "company": external_id, "url": f"https://x/{external_id}"}
    fields.update(kwargs)
    return Job("demo", external_id, **fields)


def local(*args):
    return datetime(*args).astimezone()


@pytest.mark.parametrize(
    "low, high, currency, period, expected",
    [
        (1800000.0, 2500000.0, "INR", "year", "INR 18,00,000 - 25,00,000 / year"),
        (12500000.0, None, "INR", "year", "INR 1,25,00,000 / year"),
        (900.0, None, "INR", "day", "INR 900 / day"),
        (120000.0, 150000.0, "USD", "year", "USD 120,000 - 150,000 / year"),
        (None, 45.5, "USD", "hour", "USD 45.50 / hour"),
        (90000.0, 90000.0, "EUR", "", "EUR 90,000"),
        (50000.0, 70000.0, "", "month", "50,000 - 70,000 / month"),
        (None, None, "USD", "year", ""),
    ],
)
def test_salary_text(low, high, currency, period, expected):
    pay = job("a", salary_min=low, salary_max=high, salary_currency=currency, salary_period=period)
    assert salary(pay) == expected


@pytest.mark.parametrize(
    "posted_at, expected",
    [
        (local(2026, 10, 17, 8, 0), "today"),
        (local(2026, 10, 16, 23, 0), "yesterday"),
        (local(2026, 10, 15, 0, 30), "2 days ago"),
        (local(2026, 10, 18, 1, 0), "today"),
        (None, ""),
    ],
)
def test_age(posted_at, expected):
    assert age(job("a", posted_at=posted_at), DAY) == expected


def test_print_picks_shows_salary_age_and_links():
    console = Console(file=io.StringIO(), width=200)
    pick = job("a", id=7, salary_min=1800000.0, salary_max=2500000.0, salary_currency="INR", salary_period="year",
               posted_at=datetime.now().astimezone() - timedelta(days=2))
    print_picks(console, [Match(pick, 0.75)], title="Picks")
    out = console.file.getvalue()
    assert "INR 18,00,000 - 25,00,000 / year" in out
    assert "2 days ago" in out
    assert "1. https://x/a" in out


def test_markdown_lists_jobs_with_links():
    text = markdown([Match(job("a", id=7, location="Remote"), 0.75, ["Skills: python"])], DAY)
    assert "# Job picks for 2026-10-17" in text
    assert "## 1. Python Engineer a at a" in text
    assert "Remote | score 0.75 | id 7" in text
    assert "- Skills: python" in text
    assert "https://x/a" in text


def test_markdown_shows_salary_and_posted_age():
    pick = job("a", salary_min=1800000.0, salary_max=2500000.0, salary_currency="INR", salary_period="year",
               posted_at=local(2026, 10, 15, 9, 0))
    text = markdown([Match(pick, 0.75)], DAY)
    assert "INR 18,00,000 - 25,00,000 / year" in text
    assert "posted 2 days ago" in text


def test_html_page_shows_each_pick():
    first = job("a", id=7, location="Pune, India", remote=True, salary_min=1800000.0, salary_max=2500000.0,
                salary_currency="INR", salary_period="year", posted_at=local(2026, 10, 15, 9, 0))
    second = job("b", id=8, remote=False)
    page = html_page([Match(first, 0.75, ["Skills: python, django"]), Match(second, 0.4)], DAY)
    assert "<title>Job picks for 2026-10-17</title>" in page
    assert "Saturday, 17 October 2026" in page
    assert "2 jobs picked" in page
    assert "hirejutsu applied &lt;id&gt;" in page
    assert '<a href="https://x/a" target="_blank" rel="noopener noreferrer">Python Engineer a</a>' in page
    assert '<a class="open" href="https://x/b"' in page
    assert 'class="rank">2<' in page
    assert ">a</p>" in page
    assert "Pune, India" in page
    assert page.count(">Remote<") == 1
    assert "INR 18,00,000 - 25,00,000 / year" in page
    assert "posted 2 days ago" in page
    assert "width: 75%" in page
    assert "Score 0.75" in page
    assert "<li>Skills: python, django</li>" in page
    assert "hirejutsu applied 7" in page
    assert "hirejutsu applied 8" in page


def test_html_page_escapes_job_text():
    nasty = job("a", title='<script>alert("hi")</script>', company="Fish & Chips", location="<b>Pune</b>",
                url='https://x/a?b=1&c="2"')
    page = html_page([Match(nasty, 0.5, ["<img src=x onerror=alert(1)>"])], DAY)
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert(&quot;hi&quot;)&lt;/script&gt;" in page
    assert "Fish &amp; Chips" in page
    assert "&lt;b&gt;Pune&lt;/b&gt;" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page
    assert 'href="https://x/a?b=1&amp;c=&quot;2&quot;"' in page


def test_html_page_loads_nothing_from_the_internet():
    page = html_page([Match(job("a"), 0.5), Match(job("b", url="http://y/b"), 0.4)], DAY)
    assert set(re.findall(r"https?://[^\s\"'<>]+", page)) == {"https://x/a", "http://y/b"}
    assert "src=" not in page
    assert "url(" not in page


def test_html_page_links_only_to_web_addresses():
    page = html_page([Match(job("a", url="javascript:alert(1)"), 0.5)], DAY)
    assert "javascript:" not in page


def test_write_reports_saves_markdown_and_html_by_default(tmp_path):
    paths = write_reports([Match(job("a", id=1), 0.5)], Config({}, tmp_path), DAY)
    folder = tmp_path / "reports"
    assert paths == [folder / "2026-10-17.md", folder / "2026-10-17.html"]
    assert "# Job picks for 2026-10-17" in paths[0].read_text(encoding="utf-8")
    assert "<!doctype html>" in paths[1].read_text(encoding="utf-8")


def test_write_reports_uses_configured_formats(tmp_path):
    config = Config({"report": {"formats": ["html"]}}, tmp_path)
    paths = write_reports([Match(job("a", id=1), 0.5)], config, DAY)
    assert paths == [tmp_path / "reports" / "2026-10-17.html"]
    assert not (tmp_path / "reports" / "2026-10-17.md").exists()


def export_picks():
    first = job("a", id=7, location="Pune, India", remote=True, salary_min=1800000.0, salary_max=2500000.0,
                salary_currency="INR", salary_period="year", posted_at=datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc))
    return [Match(first, 0.75, ["Skills: python", "Title matches"]), Match(job("b", id=8), 0.5)]


def test_csv_report_has_one_row_per_pick(tmp_path):
    [path] = write_reports(export_picks(), Config({"report": {"formats": ["csv"]}}, tmp_path), DAY)
    assert path == tmp_path / "reports" / "2026-10-17.csv"
    assert path.read_bytes().startswith(codecs.BOM_UTF8)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert rows[0] == {
        "rank": "1", "id": "7", "score": "0.75", "title": "Python Engineer a", "company": "a",
        "location": "Pune, India", "remote": "True", "salary_min": "1800000.0", "salary_max": "2500000.0",
        "salary_currency": "INR", "salary_period": "year", "posted_at": "2026-10-15T09:30:00+00:00",
        "url": "https://x/a", "reasons": "Skills: python; Title matches",
    }
    assert (rows[1]["rank"], rows[1]["id"], rows[1]["remote"], rows[1]["posted_at"]) == ("2", "8", "", "")


def test_json_report_has_one_object_per_pick(tmp_path):
    [path] = write_reports(export_picks(), Config({"report": {"formats": ["json"]}}, tmp_path), DAY)
    assert path == tmp_path / "reports" / "2026-10-17.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data[0] == {
        "rank": 1, "id": 7, "score": 0.75, "title": "Python Engineer a", "company": "a",
        "location": "Pune, India", "remote": True, "salary_min": 1800000.0, "salary_max": 2500000.0,
        "salary_currency": "INR", "salary_period": "year", "posted_at": "2026-10-15T09:30:00+00:00",
        "url": "https://x/a", "reasons": ["Skills: python", "Title matches"],
    }
    assert (data[1]["rank"], data[1]["id"], data[1]["remote"], data[1]["posted_at"]) == (2, 8, None, None)


def test_unknown_report_format_is_an_error(tmp_path):
    config = Config({"report": {"formats": ["md", "pdf"]}}, tmp_path)
    with pytest.raises(HirejutsuError, match="pdf"):
        write_reports([Match(job("a", id=1), 0.5)], config, DAY)
