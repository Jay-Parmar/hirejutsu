import pytest
from docx import Document

from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.resume import load_profile, read_text


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


def test_read_docx_keeps_tables_in_document_order(tmp_path):
    document = Document()
    document.add_paragraph("Priya Sharma")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(0, 1)).text = "Experience"
    table.cell(1, 0).text = "Senior Software Engineer"
    table.cell(1, 1).text = "Jan 2021 - Present"
    document.add_paragraph("Python, Django")
    document.save(tmp_path / "resume.docx")
    assert read_text(tmp_path / "resume.docx").splitlines() == [
        "Priya Sharma",
        "Experience",
        "Senior Software Engineer | Jan 2021 - Present",
        "Python, Django",
    ]


def test_read_docx_that_is_not_a_docx(tmp_path):
    (tmp_path / "resume.docx").write_bytes(b"old word file")
    with pytest.raises(HirejutsuError, match="Cannot read"):
        read_text(tmp_path / "resume.docx")
