from hirejutsu.applicant import load_applicant, template
from hirejutsu.cli import main
from hirejutsu.commands import applicant as applicant_command
from hirejutsu.config import Config

DETAILS = """
first_name: Asha
last_name: Rao
email: asha@example.com
phone: 9876543210
phone_code: "+44"
links: {github: https://github.com/asha}
work:
  - {title: Backend Engineer, company: Acme, start: 2021-04}
  - {title: Developer, company: Globex, start: 2018-07, end: 2021-03}
education:
  - {school: Pune University, degree: B.E.}
answers: {notice_period: 30 days, needs_sponsorship: no}
"""
RESUME = """Priya Sharma
Pune | priya@example.com | +91 98765 43210
linkedin.com/in/priya-sharma
"""


def make_home(tmp_path, text):
    (tmp_path / "applicant.yaml").write_text(text, encoding="utf-8")
    return str(tmp_path)


def test_applicant_shows_the_details(tmp_path, capsys):
    assert main(["--home", make_home(tmp_path, DETAILS), "applicant"]) == 0
    out = capsys.readouterr().out
    assert f"Details: {tmp_path / 'applicant.yaml'}" in out
    assert "Name: Asha Rao" in out
    assert "Email: asha@example.com" in out
    assert "Phone: +44 9876543210" in out
    assert "Links: https://github.com/asha" in out
    assert "Work: Backend Engineer at Acme; Developer at Globex" in out
    assert "Education: Pune University" in out
    assert "Answers: notice_period, needs_sponsorship" in out
    assert "Missing" not in out


def test_applicant_lists_what_is_missing(tmp_path, capsys):
    assert main(["--home", make_home(tmp_path, "first_name: Asha\n"), "applicant"]) == 0
    assert "Missing: last_name, email, phone" in capsys.readouterr().out


def test_applicant_without_a_file_says_how_to_start(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "applicant"]) == 1
    assert "hirejutsu applicant --edit" in capsys.readouterr().out


def test_edit_starts_the_file_from_the_resume(tmp_path, capsys, monkeypatch):
    opened = []
    monkeypatch.setattr(applicant_command, "edit_file", opened.append)
    (tmp_path / "resume.txt").write_text(RESUME, encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "applicant", "--edit"]) == 0
    path = tmp_path / "applicant.yaml"
    assert opened == [path]
    assert path.read_text(encoding="utf-8").startswith("# Your details")
    details = load_applicant(Config({}, tmp_path))
    assert details.name == "Priya Sharma"
    assert (details.phone_code, details.phone) == ("+91", "9876543210")
    assert details.links == {"linkedin": "https://www.linkedin.com/in/priya-sharma"}
    assert "filled in from your resume: first_name, last_name, email, phone, phone_code, linkedin" in capsys.readouterr().out


def test_edit_without_a_resume_starts_from_the_template(tmp_path, monkeypatch):
    monkeypatch.setattr(applicant_command, "edit_file", lambda path: None)
    assert main(["--home", str(tmp_path), "applicant", "--edit"]) == 0
    assert (tmp_path / "applicant.yaml").read_text(encoding="utf-8") == template()


def test_edit_keeps_an_existing_file(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(applicant_command, "edit_file", opened.append)
    home = make_home(tmp_path, "first_name: Asha\n")
    assert main(["--home", home, "applicant", "--edit"]) == 0
    assert opened == [tmp_path / "applicant.yaml"]
    assert (tmp_path / "applicant.yaml").read_text(encoding="utf-8") == "first_name: Asha\n"
