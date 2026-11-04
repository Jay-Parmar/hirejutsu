import pytest
import yaml

from hirejutsu.applicant import Applicant, Position, School, load_applicant, template
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


def config(tmp_path, text=None):
    if text is not None:
        (tmp_path / "applicant.yaml").write_text(text, encoding="utf-8")
    return Config({}, tmp_path)


def test_template_is_valid_yaml_with_every_section():
    assert SECTIONS <= set(yaml.safe_load(template()))


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
