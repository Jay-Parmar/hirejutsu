from pathlib import Path

import pytest
import yaml

from hirejutsu.config import (
    HOME_ENV,
    Config,
    ConfigError,
    deep_merge,
    init_home,
    load_config,
    resolve_home,
    template,
)
from hirejutsu.ranking import RANKING_DEFAULTS


def test_resolve_home_prefers_flag_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv(HOME_ENV, str(tmp_path / "env"))
    assert resolve_home(str(tmp_path / "flag")) == (tmp_path / "flag").resolve()


def test_resolve_home_uses_env(tmp_path, monkeypatch):
    monkeypatch.setenv(HOME_ENV, str(tmp_path / "env"))
    assert resolve_home() == (tmp_path / "env").resolve()


def test_resolve_home_default(monkeypatch):
    monkeypatch.delenv(HOME_ENV, raising=False)
    assert resolve_home() == Path("~/.hirejutsu").expanduser().resolve()


def test_deep_merge_merges_nested_dicts():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    merged = deep_merge(base, {"b": {"y": 3}, "c": 4})
    assert merged == {"a": 1, "b": {"x": 1, "y": 3}, "c": 4}
    assert base["b"]["y"] == 2


def test_load_config_without_file_is_empty(tmp_path):
    config = load_config(tmp_path)
    assert config.data == {}
    assert config.home == tmp_path


def test_load_config_reads_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text("ranking:\n  top: 5\n", encoding="utf-8")
    assert load_config(tmp_path).section("ranking") == {"top": 5}


def test_load_config_rejects_bad_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text("ranking: [\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_load_config_rejects_non_mapping(tmp_path):
    (tmp_path / "config.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_section_applies_defaults(tmp_path):
    config = Config({"ranking": {"top": 5}}, tmp_path)
    assert config.section("ranking", {"top": 10, "per_company": 2}) == {"top": 5, "per_company": 2}


def test_section_missing_or_null_uses_defaults(tmp_path):
    config = Config({"ranking": None}, tmp_path)
    assert config.section("ranking", {"top": 10}) == {"top": 10}
    assert config.section("other") == {}


def test_section_must_be_mapping(tmp_path):
    with pytest.raises(ConfigError):
        Config({"ranking": [1, 2]}, tmp_path).section("ranking")


def test_path_is_relative_to_home(tmp_path):
    config = Config({}, tmp_path)
    assert config.path("resume.pdf") == tmp_path / "resume.pdf"
    assert config.path("~/cv.pdf") == Path("~/cv.pdf").expanduser()


def test_template_is_valid_yaml():
    data = yaml.safe_load(template())
    assert isinstance(data, dict)
    assert "resume" in data


def test_template_leaves_years_to_the_resume():
    assert yaml.safe_load(template())["profile"]["years"] is None


def test_template_lists_every_ranking_setting_with_its_default():
    assert yaml.safe_load(template())["ranking"] == RANKING_DEFAULTS


def test_init_home_creates_files(tmp_path):
    home = tmp_path / "home"
    created = init_home(home)
    assert home / "config.yaml" in created
    assert (home / "config.yaml").read_text(encoding="utf-8") == template()
    assert (home / "reports").is_dir()
    assert (home / "logs").is_dir()


def test_init_home_keeps_existing_config(tmp_path):
    (tmp_path / "config.yaml").write_text("resume: mine.pdf\n", encoding="utf-8")
    assert tmp_path / "config.yaml" not in init_home(tmp_path)
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "resume: mine.pdf\n"


def test_init_home_force_overwrites(tmp_path):
    (tmp_path / "config.yaml").write_text("resume: mine.pdf\n", encoding="utf-8")
    init_home(tmp_path, force=True)
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == template()
