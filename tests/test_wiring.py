from pathlib import Path

from pytestqt.qtbot import QtBot

from onemic.config import Config
from onemic.ui.controller import AppController
from onemic.ui.main_window import MainWindow
from onemic.wiring import build_application


def test_the_application_is_wired_from_config(qtbot: QtBot, tmp_path: Path) -> None:
    built = build_application(Config(tmp_path / "onemic", tmp_path), quit_application=lambda: None)
    qtbot.addWidget(built.window)

    assert isinstance(built.window, MainWindow)
    assert isinstance(built.controller, AppController)
    assert not built.controller.status.live
    built.window.allow_close()
