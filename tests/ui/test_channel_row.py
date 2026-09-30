import pytest
from pytestqt.qtbot import QtBot

from onemic.domain.levels import LevelThresholds
from onemic.domain.waveform import WaveColumn
from onemic.services.metering import MeterReading
from onemic.services.routing import InputState
from onemic.ui.channel_row import ChannelRow, format_peak, newest_peak
from onemic.ui.theme import Palette


@pytest.fixture
def row(qtbot: QtBot) -> ChannelRow:
    widget = ChannelRow("v1", Palette(), LevelThresholds())
    qtbot.addWidget(widget)
    return widget


@pytest.mark.parametrize(("peak", "text"), [(1.0, "0.0"), (0.5, "-6.0"), (0.0, "-inf")])
def test_format_peak(peak: float, text: str) -> None:
    assert format_peak(peak) == text


def test_showing_saved_values_does_not_echo_them_as_edits(qtbot: QtBot, row: ChannelRow) -> None:
    with qtbot.assertNotEmitted(row.gain_changed), qtbot.assertNotEmitted(row.mute_toggled):
        row.set_values("Voice", 0.8, muted=True)

    assert row._slider.value() == 80
    assert row._mute.isChecked()


def test_moving_the_slider_reports_the_gain(qtbot: QtBot, row: ChannelRow) -> None:
    with qtbot.waitSignal(row.gain_changed) as signal:
        row._slider.setValue(125)

    assert signal.args == ["v1", 1.25]


def test_mute_and_remove_report_the_row_key(qtbot: QtBot, row: ChannelRow) -> None:
    with qtbot.waitSignal(row.mute_toggled) as muted:
        row._mute.click()
    with qtbot.waitSignal(row.remove_requested) as removed:
        row._remove.click()

    assert muted.args == ["v1", True]
    assert removed.args == ["v1"]


def test_readings_update_the_peak_and_its_colour(row: ChannelRow) -> None:
    row.set_reading(MeterReading((WaveColumn(-0.2, 1.0),), 1.0))

    assert row._peak.text() == "0.0"
    assert Palette().clip in row._peak.styleSheet()

    row.clear_reading()

    assert row._peak.text() == "-inf"
    assert Palette().dim in row._peak.styleSheet()


def test_state_dims_the_title_until_live(row: ChannelRow) -> None:
    row.set_state(InputState.WAITING)
    assert Palette().dim in row._title.styleSheet()
    assert "Waiting" in row.toolTip()

    row.set_state(InputState.LIVE)
    assert Palette().text in row._title.styleSheet()


def test_newest_peak_only_counts_columns_since_the_last_frame() -> None:
    history = [WaveColumn(-0.9, 0.9, 1.0), WaveColumn(-0.2, 0.2, 2.0), WaveColumn(-0.4, 0.1, 3.0)]

    assert newest_peak(history, after=1.0) == (0.4, 3.0)
    assert newest_peak(history, after=3.0) == (0.0, 3.0)


def test_the_level_meter_follows_new_audio(qtbot: QtBot) -> None:
    now = [10.0]
    widget = ChannelRow("v1", Palette(), LevelThresholds(), clock=lambda: now[0])
    qtbot.addWidget(widget)

    widget.set_reading(MeterReading((WaveColumn(-0.5, 0.5, 9.99),), 0.5))
    loud = widget.meter._level_db
    now[0] = 10.5
    widget.set_reading(MeterReading((WaveColumn(-0.5, 0.5, 9.99),), 0.5))

    assert loud == pytest.approx(-6.02, abs=0.01)
    assert widget.meter._level_db == pytest.approx(loud - 12.0, abs=0.01)


def test_solo_reports_the_row_key_and_shows_without_echo(qtbot: QtBot, row: ChannelRow) -> None:
    with qtbot.assertNotEmitted(row.solo_toggled):
        row.set_values("Voice", 1.0, muted=False, soloed=True)
    assert row._solo.isChecked()

    with qtbot.waitSignal(row.solo_toggled) as soloed:
        row._solo.click()

    assert soloed.args == ["v1", False]
