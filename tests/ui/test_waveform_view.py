from pytestqt.qtbot import QtBot

from onemic.domain.levels import Level, LevelThresholds
from onemic.domain.waveform import WaveColumn
from onemic.ui.theme import Palette
from onemic.ui.waveform import WaveformView, column_lines


def test_newest_columns_are_drawn_at_the_right_edge() -> None:
    columns = [WaveColumn(-0.1, 0.1)] * 3

    lines = column_lines(columns, width=10, height=20, thresholds=LevelThresholds())

    xs = [line.x1() for line in lines[Level.SAFE]]
    assert xs == [7.5, 8.5, 9.5]


def test_only_as_many_columns_as_pixels_are_drawn() -> None:
    lines = column_lines([WaveColumn(-0.1, 0.1)] * 50, width=10, height=20, thresholds=LevelThresholds())

    assert len(lines[Level.SAFE]) == 10


def test_columns_are_coloured_by_their_own_level() -> None:
    columns = [WaveColumn(-0.1, 0.1), WaveColumn(-0.7, 0.2), WaveColumn(-0.3, 1.2)]

    lines = column_lines(columns, width=3, height=20, thresholds=LevelThresholds())

    assert {level: len(group) for level, group in lines.items()} == {
        Level.SAFE: 1,
        Level.HOT: 1,
        Level.CLIP: 1,
    }


def test_clipped_samples_are_drawn_to_the_edge_and_no_further() -> None:
    [line] = column_lines([WaveColumn(-3.0, 3.0)], width=1, height=20, thresholds=LevelThresholds())[
        Level.CLIP
    ]

    assert (line.y1(), line.y2()) == (0.0, 20.0)


def test_silence_still_draws_a_one_pixel_line() -> None:
    [line] = column_lines([WaveColumn(0.0, 0.0)], width=1, height=20, thresholds=LevelThresholds())[
        Level.SAFE
    ]

    assert line.y2() - line.y1() == 1


def test_nothing_is_drawn_without_width() -> None:
    assert column_lines([WaveColumn(-1, 1)], width=0, height=20, thresholds=LevelThresholds()) == {}


def test_the_view_paints_its_columns(qtbot: QtBot) -> None:
    view = WaveformView(Palette(), LevelThresholds())
    qtbot.addWidget(view)
    view.resize(100, 28)

    view.set_columns([WaveColumn(-0.5, 0.5)] * 20)

    assert not view.grab().isNull()
