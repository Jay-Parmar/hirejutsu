import random
import time

from hirejutsu.models import Job, Profile
from hirejutsu.ranking import RANKING_DEFAULTS, has_term, rank


def job(external_id, title, company="Acme", description=""):
    return Job("demo", external_id, title, company, f"https://x/{external_id}", description=description, id=int(external_id))


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
    assert rank([job("1", "Engineer", description="awesome pythonic code")], PROFILE, settings()) == []


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
