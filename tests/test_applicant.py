import yaml

from hirejutsu.applicant import template

SECTIONS = {"first_name", "last_name", "email", "phone", "phone_code", "address", "links", "work", "education", "answers"}


def test_template_is_valid_yaml_with_every_section():
    assert SECTIONS <= set(yaml.safe_load(template()))
