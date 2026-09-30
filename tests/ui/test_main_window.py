import pytest
from pytestqt.qtbot import QtBot

from onemic.domain.levels import LevelThresholds
from onemic.domain.naming import MIX_TAP
from onemic.domain.profile import InputSettings, MicProfile
from onemic.domain.waveform import WaveColumn
from onemic.domain.window import Corner, WindowState
from onemic.services.metering import MeterReading
from onemic.services.routing import InputState
from onemic.services.session import SessionStatus
from onemic.ui.main_window import MainWindow
from onemic.ui.theme import Palette

INPUTS = tuple(InputSettings(f"i{n}", f"source{n}", f"Input {n}") for n in range(4))
FOUR = MicProfile("Band", INPUTS)


@pytest.fixture
def window(qtbot: QtBot) -> MainWindow:
    widget = MainWindow(Palette(), LevelThresholds(), WindowState(Corner.TOP_LEFT))
    qtbot.addWidget(widget)
    widget.show_profile(FOUR)
    widget.show()
    return widget


def test_compact_view_shows_two_inputs_and_says_how_many_are_hidden(window: MainWindow) -> None:
    assert window.visible_inputs() == ["i0", "i1"]
    assert window._more.text() == "+2 more, expand to see them"
    assert not window._more.isHidden()
    assert window._add.isHidden()


def test_expanding_shows_every_input_and_reports_the_state(qtbot: QtBot, window: MainWindow) -> None:
    with qtbot.waitSignal(window.state_changed) as signal:
        window.set_expanded(True)

    assert window.visible_inputs() == ["i0", "i1", "i2", "i3"]
    assert window._more.isHidden()
    assert not window._add.isHidden()
    assert signal.args[0].expanded


def test_an_empty_mic_offers_to_add_an_input(qtbot: QtBot) -> None:
    widget = MainWindow(Palette(), LevelThresholds(), WindowState())
    qtbot.addWidget(widget)

    widget.show_profile(MicProfile("Empty"))

    assert not widget._add.isHidden()
    assert widget.visible_inputs() == []


def test_rows_are_kept_when_only_levels_change(window: MainWindow) -> None:
    row = window._rows["i0"]

    window.show_profile(FOUR.with_input_gain("i0", 0.5))

    assert window._rows["i0"] is row
    assert row._slider.value() == 50


def test_rows_are_rebuilt_when_inputs_change(window: MainWindow) -> None:
    window.show_profile(FOUR.without_input("i0"))

    assert list(window._rows) == ["i1", "i2", "i3"]


def test_row_edits_are_forwarded_with_their_input(qtbot: QtBot, window: MainWindow) -> None:
    with qtbot.waitSignal(window.input_gain_changed) as gain:
        window._rows["i1"]._slider.setValue(30)
    with qtbot.waitSignal(window.mix_mute_toggled) as mix:
        window._mix._mute.click()

    assert gain.args == ["i1", 0.3]
    assert mix.args == [True]


def test_status_marks_each_row_and_the_window(window: MainWindow) -> None:
    window.show_status(SessionStatus("band", inputs={"i0": InputState.LIVE, "i1": InputState.WAITING}))

    assert window._live
    assert window._rows["i0"].toolTip() == "Live"
    assert "Waiting" in window._rows["i1"].toolTip()

    window.show_status(SessionStatus())

    assert not window._live
    assert window._rows["i0"].toolTip().startswith("Not live")


def test_levels_reach_visible_rows_and_the_mix(window: MainWindow) -> None:
    reading = MeterReading((WaveColumn(-0.5, 0.5),), 0.5)

    window.show_levels({"i0": reading, MIX_TAP: reading})

    assert window._rows["i0"]._peak.text() == "-6.0"
    assert window._mix._peak.text() == "-6.0"
    assert window._rows["i1"]._peak.text() == "-inf"


def test_errors_are_shown_then_hidden(qtbot: QtBot, window: MainWindow) -> None:
    window._error_timer.setInterval(10)

    window.show_error("pactl is not installed")

    assert window._error.text() == "pactl is not installed"
    assert not window._error.isHidden()
    qtbot.waitUntil(window._error.isHidden)


def test_closing_is_deferred_to_the_controller_until_allowed(qtbot: QtBot, window: MainWindow) -> None:
    with qtbot.waitSignal(window.header.close_requested):
        window.close()
    assert window.isVisible()

    window.allow_close()
    window.close()

    assert not window.isVisible()


def test_the_window_is_placed_in_its_corner(window: MainWindow) -> None:
    window.place()
    area = window.screen().availableGeometry()

    assert window.x() == area.left() + 12
    assert window.y() == area.top() + 12
