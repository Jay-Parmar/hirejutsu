from hirejutsu.cli import main

RESUME = "Senior Data Analyst, Acme, 2015 - 2020\nSQL, Python, Tableau, Excel and Power BI\n"


def make_home(tmp_path, resume=RESUME):
    (tmp_path / "resume.txt").write_text(resume, encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\n", encoding="utf-8")
    return str(tmp_path)


def test_resume_shows_what_was_found(tmp_path, capsys):
    assert main(["--home", make_home(tmp_path), "resume"]) == 0
    out = capsys.readouterr().out
    assert f"{tmp_path / 'resume.txt'} ({len(RESUME)} characters)" in out
    assert "Skills (6): SQL, Python, Tableau, Excel, Power BI, Business Intelligence" in out
    assert "Titles: Senior Data Analyst" in out
    assert "Years of experience: 5.0" in out
    assert "Locations: remote" in out
    assert "profile.skills" not in out


def test_resume_suggests_adding_skills_when_few_are_found(tmp_path, capsys):
    assert main(["--home", make_home(tmp_path, "Python developer"), "resume"]) == 0
    out = capsys.readouterr().out
    assert "Skills (1): Python" in out
    assert "profile.skills" in out


def test_resume_text_prints_the_text_as_read(tmp_path, capsys):
    assert main(["--home", make_home(tmp_path, "[b]Python[/b] :smile:"), "resume", "--text"]) == 0
    assert capsys.readouterr().out == "[b]Python[/b] :smile:\n"


def test_resume_without_a_resume_file(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "resume"]) == 2
    assert "Resume not found" in capsys.readouterr().out
