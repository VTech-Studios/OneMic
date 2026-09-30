from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from pytestqt.qtbot import QtBot

from onemic.domain.levels import Level, LevelThresholds
from onemic.ui.level_meter import LevelMeter, fraction_to_db, zones
from onemic.ui.theme import Palette


def test_a_quiet_level_lights_only_the_safe_zone() -> None:
    assert zones(-30.0, LevelThresholds()) == [(Level.SAFE, 0.0, 0.5)]


def test_a_clipping_level_lights_every_zone() -> None:
    lit = zones(0.0, LevelThresholds())

    assert [level for level, _, _ in lit] == [Level.SAFE, Level.HOT, Level.CLIP]
    assert lit[-1][2] == 1.0


def test_silence_lights_nothing() -> None:
    assert zones(-60.0, LevelThresholds()) == []


def test_the_meter_repaints_only_when_the_level_changes(qtbot: QtBot) -> None:
    meter = LevelMeter(Palette(), LevelThresholds())
    qtbot.addWidget(meter)
    meter.resize(100, 4)

    meter.set_level(-12.0, -6.0)

    assert (meter._level_db, meter._hold_db) == (-12.0, -6.0)
    assert not meter.grab().isNull()


def test_the_gate_marker_is_dragged_to_a_threshold(qtbot: QtBot) -> None:
    meter = LevelMeter(Palette(), LevelThresholds())
    qtbot.addWidget(meter)
    meter.resize(120, 10)
    meter.show()
    meter.set_gate(-45.0)

    with qtbot.waitSignal(meter.threshold_changed) as moved:
        QTest.mouseClick(meter, Qt.MouseButton.LeftButton, pos=QPoint(60, 5))

    assert moved.args == [-30.0]


def test_the_marker_cannot_be_dragged_while_the_gate_is_off(qtbot: QtBot) -> None:
    meter = LevelMeter(Palette(), LevelThresholds())
    qtbot.addWidget(meter)
    meter.resize(120, 10)
    meter.show()

    with qtbot.assertNotEmitted(meter.threshold_changed):
        QTest.mouseClick(meter, Qt.MouseButton.LeftButton, pos=QPoint(60, 5))


def test_dragged_thresholds_stay_in_the_useful_range(qtbot: QtBot) -> None:
    meter = LevelMeter(Palette(), LevelThresholds())
    qtbot.addWidget(meter)
    meter.resize(120, 10)
    meter.show()
    meter.set_gate(-45.0)

    with qtbot.waitSignal(meter.threshold_changed) as moved:
        QTest.mouseClick(meter, Qt.MouseButton.LeftButton, pos=QPoint(119, 5))

    assert moved.args == [-10.0]


def test_fraction_to_db_is_the_inverse_of_the_meter_scale() -> None:
    assert fraction_to_db(0.5) == -30.0
    assert fraction_to_db(2.0) == 0.0
