from datetime import datetime, timedelta, timezone

import pytest
from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.models import Job
from hirejutsu.sources.workday import Workday, posted_on, remote

CAREERS = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
API = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite"
NVIDIA = Company("workday", "nvidia.wd5/NVIDIAExternalCareerSite", "NVIDIA")
DAY = timedelta(days=1)


def source(tmp_path, client, max_age_days=14, **settings):
    config = board_config(
        tmp_path, "workday", [{"name": "NVIDIA", "url": CAREERS}],
        search={"max_age_days": max_age_days}, sources={"workday": settings},
    )
    return Workday(config, client)


def pages(posted: list[str], total: int):
    """A fake job list where posted[n] is the postedOn text of every job on page n."""
    item = fixture("workday.json")["jobPostings"][0]

    def answer(payload):
        page = payload["offset"] // 20
        if page >= len(posted):
            return {"total": 0, "jobPostings": []}
        jobs = [{**item, "externalPath": f"/job/x/Job_{page}_{n}", "postedOn": posted[page]} for n in range(20)]
        return {"total": total if page == 0 else 0, "jobPostings": jobs}

    return answer


@pytest.mark.parametrize("text, days", [
    ("Posted Today", 0),
    ("Posted Yesterday", 1),
    ("Posted 3 Days Ago", 3),
    ("Posted 30+ Days Ago", 30),
])
def test_posted_on(text, days):
    assert abs(posted_on(text) - (datetime.now(timezone.utc) - timedelta(days=days))) < timedelta(minutes=1)


def test_posted_on_without_a_date():
    assert posted_on("2 Locations") is None
    assert posted_on(None) is None


@pytest.mark.parametrize("remote_type, location, expected", [
    ("No", "Office - Japan - Tokyo", False),
    ("Yes", "Japan", True),
    ("Office - Flexible", "US, CA", False),
    (None, "US, WA, Remote", True),
    (None, "2 Locations", None),
])
def test_remote_type(remote_type, location, expected):
    assert remote(remote_type, location) is expected


def test_list_maps_postings(tmp_path):
    client = FakeClient({f"{API}/jobs": fixture("workday.json")})
    first, second, _ = source(tmp_path, client).board_jobs(NVIDIA)
    assert client.calls[0][3] == {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
    assert first.source == "workday"
    assert first.external_id == "nvidia:Principal-Block-File-Storage-Software-Engineer--Linux---DGX-Cloud_JR2024421"
    assert first.title == "Principal Block and File Storage Software Engineer, Linux - DGX Cloud"
    assert first.company == "NVIDIA"
    assert first.url == (
        f"{CAREERS}/job/US-CA-Santa-Clara/Principal-Block-File-Storage-Software-Engineer--Linux---DGX-Cloud_JR2024421"
    )
    assert first.location == "US, CA, Santa Clara"
    assert abs(first.posted_at - (datetime.now(timezone.utc) - DAY)) < timedelta(minutes=1)
    assert first.tags == ["JR2024421"]
    assert second.location == "2 Locations"


def test_paging_stops_at_old_jobs(tmp_path):
    client = FakeClient({f"{API}/jobs": pages(["Posted Today", "Posted 30+ Days Ago", "Posted 30+ Days Ago"], 60)})
    jobs = source(tmp_path, client).board_jobs(NVIDIA)
    assert [call[3]["offset"] for call in client.calls] == [0, 20]
    assert len(jobs) == 40


def test_paging_stops_at_the_total_and_at_max_pages(tmp_path):
    recent = ["Posted Today"] * 5
    client = FakeClient({f"{API}/jobs": pages(recent, 40)})
    assert len(source(tmp_path, client).board_jobs(NVIDIA)) == 40
    client = FakeClient({f"{API}/jobs": pages(recent, 100)})
    assert len(source(tmp_path, client, max_pages=3).board_jobs(NVIDIA)) == 60


def test_postings_without_a_path_are_skipped(tmp_path):
    data = fixture("workday.json")
    data["jobPostings"].append({"bulletFields": ["R00361925", "Location Negotiable"]})
    assert len(source(tmp_path, FakeClient({f"{API}/jobs": data})).board_jobs(NVIDIA)) == 3


def test_details_complete_the_job(tmp_path):
    path = "/job/US-CA-Santa-Clara/Principal-Software-Engineer---Large-Scale-LLM-Memory-and-Storage-Systems_JR2010271"
    listed = Job("workday", "nvidia:x", "Principal Software Engineer", "NVIDIA", CAREERS + path, location="3 Locations")
    client = FakeClient({API + path: fixture("workday_job.json")})
    job = source(tmp_path, client).job_details(NVIDIA, listed)
    assert job.title == "Principal Software Engineer \u2013 Large-Scale LLM Memory and Storage Systems"
    assert job.description.startswith("NVIDIA Dynamo is a high-throughput, low-latency inference framework")
    assert job.location == "US, CA, Santa Clara; US, WA, Remote; US, MA, Remote"
    assert job.remote is True
    assert job.posted_at == datetime(2026, 1, 9, tzinfo=timezone.utc)
    assert job.employment_type == "Full time"
    assert job.url == CAREERS + path
    assert job.external_id == "nvidia:x"


def test_probe_reads_the_total(tmp_path):
    client = FakeClient({f"{API}/jobs": fixture("workday.json")})
    assert source(tmp_path, client).probe(Company("workday", NVIDIA.slug)) == (3, "")
    assert client.calls[0][3]["limit"] == 1
