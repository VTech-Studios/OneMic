import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPolygonF
from pytestqt.qtbot import QtBot

from onemic.domain.levels import Level, LevelThresholds
from onemic.domain.waveform import WaveColumn
from onemic.ui.theme import Palette
from onemic.ui.waveform import WaveformView, place, waveform_shapes


def points(shape: QPolygonF) -> list[QPointF]:
    return [shape.at(index) for index in range(shape.size())]


def columns(*peaks: float, step: float = 0.1) -> list[WaveColumn]:
    return [WaveColumn(-peak, peak, index * step) for index, peak in enumerate(peaks)]


def test_columns_are_placed_by_time_with_the_newest_at_the_right() -> None:
    placed = place(columns(0.1, 0.1, 0.1), width=100, now=0.2, speed=10.0)

    assert [x for x, _ in placed] == pytest.approx([98.0, 99.0, 100.0])


def test_positions_move_smoothly_between_frames() -> None:
    first = place(columns(0.1), width=100, now=0.0, speed=60.0)[0][0]
    later = place(columns(0.1), width=100, now=0.004, speed=60.0)[0][0]

    assert first - later == pytest.approx(0.24)


def test_columns_scrolled_off_the_left_are_dropped() -> None:
    placed = place(columns(0.1, 0.1, 0.1, step=20.0), width=100, now=40.0, speed=10.0)

    assert len(placed) == 1


def test_audio_not_yet_due_stays_off_the_right_edge() -> None:
    assert place([WaveColumn(-0.1, 0.1, 5.0)], width=100, now=0.0, speed=10.0) == []


def test_shapes_split_where_the_level_changes_and_meet_without_gaps() -> None:
    placed = place(columns(0.1, 0.1, 0.7, 1.0, 0.1), width=100, now=0.4, speed=10.0)

    shapes = waveform_shapes(placed, height=30, thresholds=LevelThresholds())

    assert [level for level, _ in shapes] == [Level.SAFE, Level.HOT, Level.CLIP, Level.SAFE]
    first_run_right_edge = max(point.x() for point in points(shapes[0][1]))
    assert first_run_right_edge == placed[2][0]


def test_quiet_room_noise_stays_close_to_the_centre_line() -> None:
    placed = [(10.0, WaveColumn(-0.02, 0.02))]

    [(_, shape)] = waveform_shapes(placed, height=30, thresholds=LevelThresholds())

    tallest = max(point.y() for point in points(shape)) - min(point.y() for point in points(shape))
    assert tallest < 3


def test_silence_still_draws_a_line() -> None:
    [(_, shape)] = waveform_shapes([(10.0, WaveColumn(0.0, 0.0))], height=30, thresholds=LevelThresholds())

    assert max(point.y() for point in points(shape)) - min(point.y() for point in points(shape)) == 1.0


def test_nothing_to_draw_gives_no_shapes() -> None:
    assert waveform_shapes([], height=30, thresholds=LevelThresholds()) == []


def test_the_view_paints_its_columns(qtbot: QtBot) -> None:
    view = WaveformView(Palette(), LevelThresholds(), clock=lambda: 1.0)
    qtbot.addWidget(view)
    view.resize(100, 30)

    view.set_columns(columns(0.5, 0.9, 1.0))

    assert not view.grab().isNull()
