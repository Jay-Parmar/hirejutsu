import pytest
from docx import Document
from fakes import FIXTURES
from pypdf import PdfWriter

from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.resume import find_skills, load_profile, read_text


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


def test_read_pdf():
    assert read_text(FIXTURES / "resume.pdf").splitlines()[:2] == ["Priya Sharma", "Senior Software Engineer"]


def test_read_pdf_expands_ligatures():
    # The fixture writes the "fl" in Airflow as one ligature glyph, as LaTeX does.
    assert "Airflow" in read_text(FIXTURES / "resume.pdf")


def test_scanned_pdf_asks_for_a_text_resume(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(tmp_path / "resume.pdf")
    with pytest.raises(HirejutsuError, match="scanned PDF"):
        read_text(tmp_path / "resume.pdf")


def test_read_pdf_that_is_not_a_pdf(tmp_path):
    (tmp_path / "resume.pdf").write_bytes(b"not a pdf")
    with pytest.raises(HirejutsuError, match="Cannot read"):
        read_text(tmp_path / "resume.pdf")


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


def test_find_skills_uses_main_names_in_order_of_mention():
    text = "Built APIs with django and Postgres on AWS.\nPython since 2015."
    assert find_skills(text) == ["Django", "PostgreSQL", "AWS", "Python"]


def test_find_skills_counts_each_skill_once():
    assert find_skills("JS, ECMAScript and JavaScript; k8s or Kubernetes") == ["JavaScript", "Kubernetes"]


def test_find_skills_matches_whole_words_only():
    assert find_skills("pythonic code, javascripts and laws") == []


def test_find_skills_with_symbols_in_names():
    assert find_skills("c++, c# and CI/CD pipelines") == ["C++", "C#", "CI/CD"]


def test_find_skills_reads_js_libraries_as_javascript():
    assert find_skills("APIs in node.js") == ["Node.js", "JavaScript"]


def test_short_and_plain_word_skills_need_their_exact_case():
    plain = "Ready to go the extra mile, react calmly, spring into action. A swift fix, no rust, each node, c and r."
    assert find_skills(plain) == []
    skills = "Go, R, C, Swift, Rust, Spring, React, Node and Excel"
    assert find_skills(skills) == ["Go", "R", "C", "Swift", "Rust", "Spring", "React", "Node.js", "Excel"]


def test_short_skills_are_not_read_inside_joined_words():
    assert find_skills("R&D for the C-suite, Go-live, USB-C, C++ and J. R. Smith") == ["C++"]


def test_exact_case_skills_have_aliases_in_any_case():
    assert find_skills("golang, reactjs and nodejs") == ["Go", "React", "Node.js"]
