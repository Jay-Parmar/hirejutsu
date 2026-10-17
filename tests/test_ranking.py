from hirejutsu.models import Job, Profile
from hirejutsu.ranking import RANKING_DEFAULTS, rank


def job(external_id, title, company="Acme", description=""):
    return Job("demo", external_id, title, company, f"https://x/{external_id}", description=description, id=int(external_id))


def settings(**kwargs):
    return {**RANKING_DEFAULTS, **kwargs}


PROFILE = Profile(text="", skills=["python", "django", "aws"], titles=["Backend Engineer"])


def test_rank_orders_by_skill_overlap():
    jobs = [
        job("1", "Java Developer", description="Spring and Java"),
        job("2", "Backend Engineer", description="Python, Django and AWS", company="Beta"),
        job("3", "Developer", description="We use python", company="Gamma"),
    ]
    assert [match.job.external_id for match in rank(jobs, PROFILE, settings())] == ["2", "3"]


def test_rank_explains_matches():
    match = rank([job("1", "Engineer", description="Python and AWS")], PROFILE, settings())[0]
    assert match.reasons == ["Skills: python, aws"]


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
