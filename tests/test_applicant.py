import pytest
import yaml

from hirejutsu.applicant import Applicant, Position, School, found_in_resume, load_applicant, template
from hirejutsu.config import Config
from hirejutsu.errors import ConfigError

SECTIONS = {"first_name", "last_name", "email", "phone", "phone_code", "address", "links", "work", "education", "answers"}
DETAILS = """
first_name: Asha
last_name: Rao
email: asha@example.com
phone: 9876543210
phone_code: +44
links: {github: https://github.com/asha, portfolio: }
work:
  - {title: Backend Engineer, company: Acme, location: Pune, start: 2021-04, end: }
education:
  - {school: Pune University, degree: B.E., field_of_study: Computer Engineering, start: 2014, end: 2018}
answers: {notice_period: 30 days, authorized_to_work: yes, needs_sponsorship: no, expected_salary: }
"""
RESUME = """Priya Sharma
Senior Software Engineer
Pune, India | priya.sharma@example.com | +91 98765 43210
linkedin.com/in/priya-sharma | https://github.com/priyasharma
Jan 2021 - Present
"""


def config(tmp_path, text=None):
    if text is not None:
        (tmp_path / "applicant.yaml").write_text(text, encoding="utf-8")
    return Config({}, tmp_path)


def test_template_is_valid_yaml_with_every_section():
    assert SECTIONS <= set(yaml.safe_load(template()))


def test_template_has_empty_answers_for_workday_forms():
    answers = yaml.safe_load(template())["answers"]
    for key in ("worked_here_before", "gender", "ethnicity", "veteran_status", "disability"):
        assert key in answers
        assert answers[key] is None


def test_no_file_means_no_details(tmp_path):
    assert load_applicant(config(tmp_path)) == Applicant()


def test_starter_file_loads_as_empty_details(tmp_path):
    applicant = load_applicant(config(tmp_path, template()))
    assert applicant.name == ""
    assert applicant.work == []
    assert applicant.education == []
    assert applicant.answers == {}
    assert applicant.phone_code == "+91"
    assert applicant.address == {"country": "India"}


def test_details_are_read_as_text(tmp_path):
    applicant = load_applicant(config(tmp_path, DETAILS))
    assert applicant.name == "Asha Rao"
    assert applicant.phone == "9876543210"
    assert applicant.phone_code == "+44"
    assert applicant.links == {"github": "https://github.com/asha"}
    assert applicant.work == [Position("Backend Engineer", "Acme", location="Pune", start="2021-04")]
    assert applicant.education == [School("Pune University", "B.E.", "Computer Engineering", "2014", "2018")]
    assert applicant.answers == {"notice_period": "30 days", "authorized_to_work": "Yes", "needs_sponsorship": "No"}


def test_setting_points_to_another_file(tmp_path):
    (tmp_path / "me.yaml").write_text("first_name: Asha\n", encoding="utf-8")
    assert load_applicant(Config({"applicant": "me.yaml"}, tmp_path)).first_name == "Asha"


def test_bad_yaml_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="applicant.yaml"):
        load_applicant(config(tmp_path, "first_name: [\n"))


def test_work_must_be_a_list(tmp_path):
    with pytest.raises(ConfigError, match="'work'.* must be a list"):
        load_applicant(config(tmp_path, "work: Acme\n"))


def test_job_needs_title_and_company(tmp_path):
    with pytest.raises(ConfigError, match="needs title and company"):
        load_applicant(config(tmp_path, "work:\n  - {title: Engineer}\n"))


def test_unknown_keys_are_reported(tmp_path):
    with pytest.raises(ConfigError, match="'titel'"):
        load_applicant(config(tmp_path, "work:\n  - {titel: Engineer, title: Engineer, company: Acme}\n"))


def test_details_are_found_in_a_resume():
    assert found_in_resume(RESUME) == {
        "first_name": "Priya",
        "last_name": "Sharma",
        "email": "priya.sharma@example.com",
        "phone_code": "+91",
        "phone": "9876543210",
        "linkedin": "https://www.linkedin.com/in/priya-sharma",
        "github": "https://github.com/priyasharma",
    }


def test_names_in_capitals_are_written_normally():
    found = found_in_resume("JAY KUMAR PARMAR\nDeveloper")
    assert (found["first_name"], found["last_name"]) == ("Jay Kumar", "Parmar")


def test_a_heading_is_not_taken_for_a_name():
    assert "first_name" not in found_in_resume("Curriculum Vitae\npriya@example.com")
    assert "first_name" not in found_in_resume("Resume 2026\npriya@example.com")


def test_phone_without_a_country_code():
    found = found_in_resume("Call 98765-43210")
    assert found["phone"] == "9876543210"
    assert "phone_code" not in found


def test_dates_are_not_phone_numbers():
    assert "phone" not in found_in_resume("Acme 2018 - 2020\nGlobex 2020 - 2024")
    assert "phone" not in found_in_resume("Acme\n2018 - 2020\n2021 - 2024")
