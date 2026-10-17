from datetime import datetime, timedelta, timezone

import pytest
from fakes import FakeClient

from hirejutsu import sources
from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.sources import Query, Source, load_sources
from hirejutsu.sources.base import url_id


class Alpha(Source):
    name = "alpha"


class Beta(Source):
    name = "beta"
    defaults = {"enabled": False, "pages": 2}


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setitem(sources.SOURCES, "alpha", Alpha)
    monkeypatch.setitem(sources.SOURCES, "beta", Beta)


def config(tmp_path, **data):
    return Config(data, tmp_path)


def test_query_uses_search_keywords(tmp_path):
    query = Query.from_config(config(tmp_path, search={"keywords": ["python"]}, profile={"titles": ["Engineer"]}))
    assert query.keywords == ["python"]


def test_query_falls_back_to_titles(tmp_path):
    query = Query.from_config(config(tmp_path, profile={"titles": ["Backend Engineer"], "locations": ["Remote", "Pune"]}))
    assert query.keywords == ["Backend Engineer"]
    assert query.locations == ["Remote", "Pune"]
    assert query.wants_remote


def test_query_defaults(tmp_path):
    query = Query.from_config(config(tmp_path))
    assert query.keywords == []
    assert query.max_age_days == 14
    assert not query.wants_remote


def test_query_is_recent_uses_max_age():
    query = Query(max_age_days=7)
    now = datetime.now(timezone.utc)
    assert query.is_recent(now - timedelta(days=6))
    assert not query.is_recent(now - timedelta(days=8))


def test_query_is_recent_keeps_undated_jobs():
    assert Query(max_age_days=7).is_recent(None)


def test_url_id_is_short_and_stable():
    first = url_id("https://example.com/jobs/1")
    assert first == url_id("https://example.com/jobs/1")
    assert first != url_id("https://example.com/jobs/2")
    assert len(first) == 16


def test_source_settings_merge_defaults(tmp_path):
    beta = Beta(config(tmp_path, sources={"beta": {"enabled": True}}), FakeClient())
    assert beta.settings == {"enabled": True, "pages": 2}


def test_source_settings_accept_bool(tmp_path):
    assert Alpha(config(tmp_path, sources={"alpha": False}), FakeClient()).settings["enabled"] is False


def test_load_sources_returns_enabled_only(tmp_path, registry):
    loaded = load_sources(config(tmp_path, sources={"alpha": True}), FakeClient())
    assert [source.name for source in loaded if source.name in ("alpha", "beta")] == ["alpha"]


def test_load_sources_by_name_ignores_enabled(tmp_path, registry):
    loaded = load_sources(config(tmp_path), FakeClient(), names=["beta"])
    assert [source.name for source in loaded] == ["beta"]


def test_load_sources_unknown_name(tmp_path, registry):
    with pytest.raises(HirejutsuError):
        load_sources(config(tmp_path), FakeClient(), names=["nope"])
