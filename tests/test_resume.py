import pytest

from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.resume import load_profile


def test_load_profile_reads_text_resume(tmp_path):
    (tmp_path / "resume.txt").write_text("Python developer\nDjango, AWS", encoding="utf-8")
    profile = load_profile(Config({"resume": "resume.txt"}, tmp_path))
    assert "Django" in profile.text
    assert profile.locations == ["remote"]


def test_load_profile_uses_config_values(tmp_path):
    (tmp_path / "cv.md").write_text("# Me", encoding="utf-8")
    config = Config(
        {
            "resume": "cv.md",
            "profile": {"titles": ["Backend Engineer"], "skills": ["Go"], "locations": ["Pune"], "years": 4},
        },
        tmp_path,
    )
    profile = load_profile(config)
    assert profile.titles == ["Backend Engineer"]
    assert profile.skills == ["Go"]
    assert profile.locations == ["Pune"]
    assert profile.years == 4


def test_missing_resume(tmp_path):
    with pytest.raises(HirejutsuError, match="not found"):
        load_profile(Config({"resume": "nope.txt"}, tmp_path))


def test_unsupported_resume_type(tmp_path):
    (tmp_path / "resume.rtf").write_text("x", encoding="utf-8")
    with pytest.raises(HirejutsuError, match=".rtf"):
        load_profile(Config({"resume": "resume.rtf"}, tmp_path))
