import pytest

from hirejutsu import __version__
from hirejutsu.cli import main


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 1
    assert "usage" in capsys.readouterr().out


def test_init_creates_config(tmp_path, capsys):
    home = tmp_path / "home"
    assert main(["--home", str(home), "init"]) == 0
    assert (home / "config.yaml").exists()
    assert "Created" in capsys.readouterr().out


def test_init_twice_keeps_config(tmp_path, capsys):
    main(["--home", str(tmp_path), "init"])
    (tmp_path / "config.yaml").write_text("resume: mine.pdf\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "init"]) == 0
    assert "already exists" in capsys.readouterr().out
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == "resume: mine.pdf\n"


def test_config_prints_path(tmp_path, capsys):
    main(["--home", str(tmp_path), "init"])
    capsys.readouterr()
    assert main(["--home", str(tmp_path), "config"]) == 0
    assert str(tmp_path / "config.yaml") in capsys.readouterr().out


def test_config_without_init(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "config"]) == 1
    assert "hirejutsu init" in capsys.readouterr().out


def test_bad_config_reports_error(tmp_path, capsys):
    (tmp_path / "config.yaml").write_text("- not a mapping\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "config"]) == 2
    assert "error" in capsys.readouterr().out
