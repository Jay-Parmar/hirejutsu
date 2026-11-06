import json
import sys
from contextlib import contextmanager

from fakes import FakePage
from hirejutsu import browser
from hirejutsu.cli import main
from hirejutsu.workday import Field

DETAILS = "first_name: Asha\nlast_name: Rao\nemail: asha@example.com\nphone: 9876543210\n"
LINK = "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Pune/Engineer_R1"


def make_home(tmp_path, resume="resume.txt"):
    (tmp_path / "applicant.yaml").write_text(DETAILS, encoding="utf-8")
    (tmp_path / resume).write_text("Asha Rao\nBackend Engineer\nPython, Django, AWS\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(f"resume: {resume}\n", encoding="utf-8")
    return str(tmp_path)


def information(*steps):
    fields = [Field(1, ("legalName--firstName",), "Given Name(s)", required=True), Field(2, ("extension",), "Phone Extension")]
    return FakePage(fields, steps=steps or ["current step 2 of 3 My Information", "current step 3 of 3 Review"])


def fake_window(monkeypatch, page):
    """Opens page instead of a browser, and returns the settings each window was opened with."""
    opened = []

    @contextmanager
    def open_window(settings, headless=False):
        opened.append(settings)
        yield page

    monkeypatch.setattr(browser, "open_window", open_window)
    return opened


def test_each_step_is_filled_until_the_review_step(tmp_path, capsys, monkeypatch):
    page = information()
    opened = fake_window(monkeypatch, page)
    assert main(["--home", make_home(tmp_path), "workday", "acme.wd5.myworkdayjobs.com/en-US/External/job/Pune/Engineer_R1"]) == 0
    out = capsys.readouterr().out
    assert page.url == LINK
    assert opened[0]["profile_folder"] == tmp_path.resolve() / "browser"
    assert "My Information: filled 1 field" in out
    assert "Given Name(s): Asha" in out
    assert "Left for you: Phone Extension" in out
    assert "Filled 1 field on 1 step. Check the Review step and submit it yourself." in out


def test_closing_the_window_early_still_tells_what_was_filled(tmp_path, capsys, monkeypatch):
    fake_window(monkeypatch, information("current step 2 of 3 My Information", ""))
    assert main(["--home", make_home(tmp_path), "workday", LINK]) == 0
    assert "The window was closed. Filled 1 field on 1 step." in capsys.readouterr().out


def test_dump_saves_the_fields_of_each_step(tmp_path, capsys, monkeypatch):
    fake_window(monkeypatch, information())
    main(["--home", make_home(tmp_path), "workday", LINK, "--dump"])
    saved = list((tmp_path / "logs").glob("workday-*-my-information.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text(encoding="utf-8"))["fields"][0]["label"] == "Given Name(s)"
    assert "Asha" not in saved[0].read_text(encoding="utf-8")
    assert f"Saved the fields of My Information to {saved[0]}" in capsys.readouterr().out


def test_a_resume_workday_cannot_read_is_left_for_you(tmp_path, capsys, monkeypatch):
    fake_window(monkeypatch, information())
    main(["--home", make_home(tmp_path), "workday", LINK])
    assert "Workday takes a PDF or DOCX resume, so resume.txt is left for you to upload." in capsys.readouterr().out


def test_without_a_resume_the_rest_is_still_filled(tmp_path, capsys, monkeypatch):
    page = information()
    fake_window(monkeypatch, page)
    home = make_home(tmp_path)
    (tmp_path / "resume.txt").unlink()
    assert main(["--home", home, "workday", LINK]) == 0
    assert "Skills and the resume upload are left for you." in capsys.readouterr().out
    assert page.value(1) == "Asha"


def test_workday_needs_applicant_details(tmp_path, capsys, monkeypatch):
    fake_window(monkeypatch, information())
    assert main(["--home", str(tmp_path), "workday", LINK]) == 1
    assert "hirejutsu applicant --edit" in capsys.readouterr().out


def test_without_playwright_you_are_told_how_to_get_it(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    assert main(["--home", make_home(tmp_path), "workday", LINK]) == 2
    assert 'pip install -e ".[workday]"' in capsys.readouterr().out
