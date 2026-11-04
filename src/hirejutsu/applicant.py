"""Your details for job applications, kept in applicant.yaml in the data folder."""

from importlib import resources

APPLICANT_NAME = "applicant.yaml"


def template() -> str:
    return resources.files("hirejutsu").joinpath("data", APPLICANT_NAME).read_text(encoding="utf-8")
