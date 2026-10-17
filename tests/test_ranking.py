import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from hirejutsu.models import Job, Profile
from hirejutsu.ranking import RANKING_DEFAULTS, has_term, rank

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def job(external_id, title, company="Acme", description="", **fields):
    return Job("demo", external_id, title, company, f"https://x/{external_id}", description=description,
               id=int(external_id), **fields)


def settings(**kwargs):
    return {**RANKING_DEFAULTS, **kwargs}


PROFILE = Profile(text="", skills=["python", "django", "aws"], titles=["Backend Engineer"])

VOCAB = (
    "python django kafka aws docker react java go postgresql redis we build scalable reliable services for "
    "customers you will own features end to end with product design and data teams review code mentor "
    "engineers improve our systems cloud infrastructure distributed apis testing observability"
).split()
MANY_SKILLS = [
    "python", "django", "kafka", "aws", "docker", "react", "java", "go", "postgresql", "redis", "c++", "c#",
    "node.js", "machine learning", "ci/cd", ".net", "elixir", "haskell", "scala", "spark", "airflow",
    "terraform", "kubernetes", "graphql", "rust", "flutter", "swift", "kotlin", "php", "ruby",
]


def synthetic_jobs(count):
    rng = random.Random(7)
    titles = ["Backend Engineer", "Senior Software Engineer", "Data Engineer", "Frontend Developer", "Sales Engineer"]
    return [
        Job("demo", str(n), rng.choice(titles), f"Company {n % 1000}", f"https://x/{n}",
            description=" ".join(rng.choices(VOCAB, k=300)), id=n)
        for n in range(count)
    ]


def test_has_term_needs_word_boundaries():
    assert has_term("we use python daily", "python")
    assert has_term("python", "python")
    assert not has_term("pythonic code in python3", "python")
    assert has_term("pythonic code, then python.", "python")


def test_has_term_handles_symbols():
    assert has_term("c++ and node.js", "c++")
    assert has_term("c++ and node.js", "node.js")
    assert has_term("node.js", "node")
    assert not has_term("abc++", "c++")


def test_rank_handles_twenty_thousand_jobs_quickly():
    jobs = synthetic_jobs(20_000)
    profile = Profile(text=" ".join(VOCAB), skills=MANY_SKILLS, titles=["Backend Engineer"])
    start = time.perf_counter()
    matches = rank(jobs, profile, settings())
    assert time.perf_counter() - start < 5
    assert len(matches) == 10


def test_rank_orders_by_skill_overlap():
    jobs = [
        job("1", "Java Developer", description="Spring and Java"),
        job("2", "Backend Engineer", description="Python, Django and AWS", company="Beta"),
        job("3", "Developer", description="We use python", company="Gamma"),
    ]
    assert [match.job.external_id for match in rank(jobs, PROFILE, settings())] == ["2", "3"]


def test_rank_explains_matches():
    match = rank([job("1", "Engineer", description="Python and AWS")], PROFILE, settings())[0]
    assert match.reasons == ["Skills: python, aws (2 of 3)"]


def test_rare_skills_count_more_than_common_ones():
    jobs = [
        job("1", "Engineer", company="A", description="python django"),
        job("2", "Engineer", company="B", description="python django"),
        job("3", "Engineer", company="C", description="python kafka"),
    ]
    matches = rank(jobs, Profile(skills=["python", "django", "kafka"]), settings())
    assert matches[0].job.external_id == "3"


def test_skill_in_the_title_counts_more():
    jobs = [
        job("1", "Backend Engineer", company="A", description="python and django"),
        job("2", "Python Engineer", company="B", description="python and django"),
    ]
    assert rank(jobs, Profile(skills=["python", "django", "kafka"]), settings())[0].job.external_id == "2"


def test_long_skill_lists_still_reach_full_marks():
    skills = [f"skill{n}" for n in range(16)]
    jobs = [
        job("1", "Engineer", company="A", description=" ".join(skills[:8])),
        job("2", "Engineer", company="B", description=" ".join(skills[8:])),
    ]
    matches = rank(jobs, Profile(skills=skills), settings(weights={"skills": 1}))
    assert [match.score for match in matches] == [1.0, 1.0]


def test_skills_reason_names_the_rarest_three():
    jobs = [
        job("1", "Engineer", company="A", description="python django aws kafka redis"),
        job("2", "Engineer", company="B", description="python django aws"),
        job("3", "Engineer", company="C", description="python django"),
    ]
    matches = rank(jobs, Profile(skills=["python", "django", "aws", "kafka", "redis"]), settings())
    assert matches[0].reasons == ["Skills: kafka, redis, aws (5 of 5)"]


def test_rank_matches_whole_words_only():
    assert rank([job("1", "Analyst", description="awesome pythonic code")], PROFILE, settings()) == []


def test_close_titles_rank_higher():
    jobs = [
        job("1", "Sales Engineer", company="A", description="python"),
        job("2", "Senior Backend Engineer", company="B", description="python"),
    ]
    matches = rank(jobs, PROFILE, settings())
    assert [match.job.external_id for match in matches] == ["2", "1"]
    assert "Title close to Backend Engineer" in matches[0].reasons


def test_title_spells_out_abbreviations():
    profile = Profile(skills=["python"], titles=["Backend Engineer", "Full Stack Developer"])
    jobs = [
        job("1", "Sr. Backend Eng", company="A", description="python"),
        job("2", "Fullstack Dev II", company="B", description="python"),
    ]
    assert [match.score for match in rank(jobs, profile, settings(weights={"title": 1}))] == [1.0, 1.0]


def test_close_title_counts_without_skills():
    jobs = [job("1", "Backend Engineer", company="A"), job("2", "Data Analyst", company="B")]
    assert [match.job.external_id for match in rank(jobs, PROFILE, settings())] == ["1"]


def test_shared_common_words_do_not_make_titles_close():
    titles = ["Backend Engineer", "Frontend Engineer", "Sales Engineer", "Data Engineer"]
    jobs = [job(str(n), title, company=title, description="python") for n, title in enumerate(titles, start=1)]
    matches = rank(jobs, PROFILE, settings())
    close = [match.job.title for match in matches if any(reason.startswith("Title") for reason in match.reasons)]
    assert close == ["Backend Engineer"]


def test_rank_limits_jobs_per_company():
    jobs = [job(str(n), f"Backend Engineer {n}", description="python django") for n in range(1, 5)]
    assert len(rank(jobs, PROFILE, settings(per_company=2))) == 2


def test_rank_returns_top_n():
    jobs = [job(str(n), "Backend Engineer", company=f"C{n}", description="python") for n in range(1, 20)]
    assert len(rank(jobs, PROFILE, settings(top=5))) == 5


def test_rank_skips_duplicate_listings():
    jobs = [
        job("1", "Backend Engineer", description="python"),
        Job("other", "9", "Backend Engineer", "Acme", "https://y/9", description="python", id=9),
    ]
    assert len(rank(jobs, PROFILE, settings(per_company=5))) == 1


def test_jobs_far_above_your_years_rank_lower():
    jobs = [
        job("1", "Staff Engineer", company="A", description="python"),
        job("2", "Engineer", company="B", description="python, 3+ years of experience"),
    ]
    matches = rank(jobs, Profile(skills=["python"], years=3), settings())
    assert [match.job.external_id for match in matches] == ["2", "1"]


@pytest.mark.parametrize("asks, reason", [
    ("3+ years of experience", "Asks 3+ years, you have 2"),
    ("5-7 years of experience", "Asks 5-7 years, you have 2"),
    ("5\N{EN DASH}7 years of experience", "Asks 5-7 years, you have 2"),
    ("3 to 5 years", "Asks 3-5 years, you have 2"),
    ("minimum of 4 years in backend", "Asks 4+ years, you have 2"),
    ("at least 6 yrs", "Asks 6+ years, you have 2"),
    ("5 years of relevant experience", "Asks 5+ years, you have 2"),
])
def test_seniority_reads_years_asked(asks, reason):
    match = rank([job("1", "Engineer", description=f"python. {asks}")], Profile(skills=["python"], years=2), settings())[0]
    assert reason in match.reasons


def test_years_about_the_company_are_not_asked():
    jobs = [job("1", "Engineer", description="python. Founded 12 years ago, 25+ years of experience serving clients")]
    match = rank(jobs, Profile(skills=["python"], years=2), settings(weights={"seniority": 1}))[0]
    assert match.score == 0.5
    assert match.reasons == ["Skills: python (1 of 1)"]


def test_seniority_is_neutral_without_your_years():
    jobs = [job("1", "Staff Engineer", description="python, 8+ years")]
    assert rank(jobs, Profile(skills=["python"]), settings(weights={"seniority": 1}))[0].score == 0.5


def test_seniority_within_tolerance_scores_full():
    jobs = [job("1", "Senior Engineer", description="python, 5+ years")]
    match = rank(jobs, Profile(skills=["python"], years=4), settings(weights={"seniority": 1}))[0]
    assert match.score == 1.0
    assert "Asks 5+ years, you have 4" in match.reasons


def test_junior_roles_rank_lower_for_experienced_people():
    jobs = [job("1", "Junior Python Developer", description="python")]
    match = rank(jobs, Profile(skills=["python"], years=10), settings(weights={"seniority": 1}))[0]
    assert match.score < 0.5
    assert "Asks junior level, you have 10 years" in match.reasons


def test_newer_jobs_rank_higher():
    jobs = [
        job("1", "Engineer", company="A", description="python", posted_at=NOW - timedelta(days=10)),
        job("2", "Engineer", company="B", description="python", posted_at=NOW - timedelta(days=1)),
    ]
    matches = rank(jobs, Profile(skills=["python"]), settings(), now=NOW)
    assert [match.job.external_id for match in matches] == ["2", "1"]


def test_freshness_halves_every_half_life():
    jobs = [
        job("1", "Engineer", company="A", description="python", posted_at=NOW - timedelta(days=3)),
        job("2", "Engineer", company="B", description="python", posted_at=NOW - timedelta(days=6)),
    ]
    matches = rank(jobs, Profile(skills=["python"]), settings(weights={"freshness": 1}, half_life_days=3), now=NOW)
    assert [match.score for match in matches] == [0.5, 0.25]


def test_freshness_uses_first_seen_without_a_post_date():
    jobs = [job("1", "Engineer", description="python", first_seen=NOW - timedelta(days=3))]
    assert rank(jobs, Profile(skills=["python"]), settings(weights={"freshness": 1}), now=NOW)[0].score == 0.5


def test_freshness_is_neutral_without_dates():
    jobs = [job("1", "Engineer", description="python")]
    assert rank(jobs, Profile(skills=["python"]), settings(weights={"freshness": 1}), now=NOW)[0].score == 0.5


@pytest.mark.parametrize("age, reason", [
    (timedelta(hours=5), "Posted today"),
    (timedelta(days=1, hours=2), "Posted yesterday"),
    (timedelta(days=2, hours=3), "Posted 2 days ago"),
])
def test_freshness_reason_says_when_it_was_posted(age, reason):
    jobs = [job("1", "Engineer", description="python", posted_at=NOW - age)]
    assert reason in rank(jobs, Profile(skills=["python"]), settings(), now=NOW)[0].reasons
