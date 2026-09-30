from pytestqt.qtbot import QtBot

from onemic.domain.levels import Level, LevelThresholds
from onemic.ui.level_meter import LevelMeter, zones
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
