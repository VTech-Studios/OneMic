from pathlib import Path

import pytest

from onemic import app
from onemic.config import REQUIRED_TOOLS, Config


def test_paths_follow_xdg() -> None:
    config = Config.from_environment(
        {"HOME": "/home/u", "XDG_CONFIG_HOME": "/cfg", "XDG_RUNTIME_DIR": "/run/u"}
    )

    assert config.profiles_path == Path("/cfg/onemic/mics.json")
    assert config.window_path == Path("/cfg/onemic/window.json")
    assert config.lock_path == Path("/run/u/onemic.lock")


def test_paths_fall_back_to_home() -> None:
    config = Config.from_environment({"HOME": "/home/u"})

    assert config.config_dir == Path("/home/u/.config/onemic")
    assert config.runtime_dir == Path("/home/u/.config")


def test_missing_tools_are_listed() -> None:
    assert app.missing_tools(lambda tool: None if tool in {"pactl", "wpctl"} else "/usr/bin/x") == [
        "pactl",
        "wpctl",
    ]
    assert app.missing_tools(lambda tool: "/usr/bin/x") == []
    assert "pw-cli" in REQUIRED_TOOLS


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        app.parse_arguments(["--version"])

    assert "onemic 1.0.0" in capsys.readouterr().out


def test_verbose_flag() -> None:
    assert app.parse_arguments(["--verbose"]).verbose
    assert not app.parse_arguments([]).verbose
