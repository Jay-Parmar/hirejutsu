from pathlib import Path

from hirejutsu import outreach
from hirejutsu.config import Config
from hirejutsu.models import Job, Match


def settings(**values):
    return outreach.load_settings(Config({"outreach": values}, Path(".")))


def pick(source, **fields):
    values = {"title": "Backend Engineer", "company": "Acme", "url": "https://jobs.acme.com/1"}
    values.update(fields)
    return Match(Job(source, "1", **values, id=12), 0.8, ["Skills: Python, Django, PostgreSQL (5 of 20)"])


def test_board_picks_are_left_out_by_default():
    picks = [pick("greenhouse"), pick("remoteok"), pick("hackernews"), pick("linkedin"), pick("workday")]
    kept = outreach.picks_to_write(picks, settings())
    assert [match.job.source for match in kept] == ["greenhouse", "hackernews", "workday"]


def test_sources_setting_changes_the_list():
    kept = outreach.picks_to_write([pick("greenhouse"), pick("remoteok")], settings(sources=["remoteok"]))
    assert [match.job.source for match in kept] == ["remoteok"]
