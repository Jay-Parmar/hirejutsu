import pytest

from hirejutsu.companies import detect, find_boards


@pytest.mark.parametrize("url, expected", [
    ("https://job-boards.greenhouse.io/stripe/jobs/8262032", ("greenhouse", "stripe")),
    ("https://boards.greenhouse.io/stripe", ("greenhouse", "stripe")),
    ("https://job-boards.eu.greenhouse.io/polyai/jobs/4567", ("greenhouse", "polyai")),
    ("https://boards.greenhouse.io/embed/job_board?for=airbnb", ("greenhouse", "airbnb")),
    ("https://boards.greenhouse.io/embed/job_app?for=airbnb&token=123", ("greenhouse", "airbnb")),
    ("https://boards-api.greenhouse.io/v1/boards/stripe/jobs", ("greenhouse", "stripe")),
    ("https://jobs.lever.co/palantir/0b5a6c1e-7d9b-4c0e-9f1a-2b3c4d5e6f70/apply", ("lever", "palantir")),
    ("https://jobs.eu.lever.co/diabolocom/0b5a6c1e", ("lever", "diabolocom")),
    ("https://api.lever.co/v0/postings/zoox?mode=json", ("lever", "zoox")),
    ("https://jobs.ashbyhq.com/ramp/d84bbf19-572a-499c-9c87-0c154ce85caf", ("ashby", "ramp")),
    ("https://jobs.ashbyhq.com/hippocratic%20ai/123/application", ("ashby", "hippocratic ai")),
    ("https://jobs.ashbyhq.com/mistral.ai", ("ashby", "mistral.ai")),
    ("https://jobs.smartrecruiters.com/ServiceNow/744000156093019-principal-engineer", ("smartrecruiters", "ServiceNow")),
    ("https://careers.smartrecruiters.com/LinkedIn3", ("smartrecruiters", "LinkedIn3")),
    ("https://channable.recruitee.com/o/talent-acquisition-partner", ("recruitee", "channable")),
    ("https://apply.workable.com/huggingface/j/81B46579FE/", ("workable", "huggingface")),
    ("https://apply.workable.com/api/v1/widget/accounts/huggingface", ("workable", "huggingface")),
    ("https://huggingface.workable.com/j/81B46579FE", ("workable", "huggingface")),
    ("https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", ("workday", "nvidia.wd5/NVIDIAExternalCareerSite")),
    ("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Engineer_JR1",
     ("workday", "nvidia.wd5/NVIDIAExternalCareerSite")),
    ("https://wd5.myworkdaysite.com/en-US/recruiting/microchiphr/External/job/AZ/Engineer_R1",
     ("workday", "microchiphr.wd5/External")),
    ("https://tado.jobs.personio.de/job/2502124", ("personio", "tado")),
    ("https://tado.jobs.personio.com/", ("personio", "tado")),
    ("https://breezy.breezy.hr/p/98323abf2296-employee-12", ("breezy", "breezy")),
    ("https://nomadic.bamboohr.com/careers/27", ("bamboohr", "nomadic")),
    ("https://quinyx.teamtailor.com/jobs/8505736-product-marketing-director", ("teamtailor", "quinyx")),
    ("jobs.lever.co/palantir", ("lever", "palantir")),
])
def test_detect_board_from_url(url, expected):
    assert detect(url) == expected


@pytest.mark.parametrize("url", [
    "https://boards.greenhouse.io/embed/job_app?token=123",
    "https://stripe.com/jobs/search?gh_jid=8172510",
    "https://apply.workable.com/j/81B46579FE",
    "https://www.bamboohr.com/pricing",
    "http://app.greenhouse.io/ai_opt_out_request/job_post/8262032/ai_opt_out",
    "https://jobs.lever.co/",
    "https://example.com/careers",
    "stripe",
])
def test_detect_ignores_urls_without_a_board(url):
    assert detect(url) is None


def test_detect_ats_and_board_text():
    assert detect("greenhouse:stripe") == ("greenhouse", "stripe")
    assert detect(" Lever:Palantir ") == ("lever", "Palantir")
    assert detect("workday:nvidia.wd5/NVIDIAExternalCareerSite") == ("workday", "nvidia.wd5/NVIDIAExternalCareerSite")
    assert detect("monster:acme") is None
    assert detect("greenhouse:") is None


def test_find_boards_in_text():
    text = (
        "Apply at https://jobs.lever.co/acme/123. Or see https://acme.breezy.hr/p/1-dev, "
        "and https://example.com/about (not a board)."
    )
    assert find_boards(text) == {("lever", "acme"), ("breezy", "acme")}
