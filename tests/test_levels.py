import math

import pytest

from onemic.domain.levels import SILENCE_DB, Level, LevelThresholds, PeakHold, amplitude_to_db


@pytest.mark.parametrize(
    ("amplitude", "expected"),
    [(1.0, 0.0), (0.5, -6.02), (0.1, -20.0), (0.0, SILENCE_DB), (-1.0, SILENCE_DB), (1e-9, SILENCE_DB)],
)
def test_amplitude_to_db(amplitude: float, expected: float) -> None:
    assert amplitude_to_db(amplitude) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(
    ("peak", "level"),
    [
        (0.0, Level.SAFE),
        (0.3, Level.SAFE),
        (0.49, Level.SAFE),
        (0.6, Level.HOT),
        (0.9, Level.HOT),
        (0.99, Level.CLIP),
        (1.4, Level.CLIP),
    ],
)
def test_default_thresholds_grade_peaks(peak: float, level: Level) -> None:
    assert LevelThresholds().classify(peak) is level


def test_thresholds_can_be_moved() -> None:
    strict = LevelThresholds(hot_db=-18.0, clip_db=-6.0)

    assert strict.classify(0.2) is Level.HOT
    assert strict.classify(0.6) is Level.CLIP


def test_peak_hold_keeps_the_highest_peak_during_the_hold() -> None:
    hold = PeakHold(hold_seconds=1.0)
    hold.update(0.8, now=0.0)
    hold.update(0.2, now=0.5)

    assert hold.peak == 0.8


def test_peak_hold_falls_to_the_latest_peak_once_the_hold_expires() -> None:
    hold = PeakHold(hold_seconds=1.0)
    hold.update(0.8, now=0.0)
    hold.update(0.2, now=1.5)

    assert hold.peak == 0.2


def test_a_higher_peak_restarts_the_hold() -> None:
    hold = PeakHold(hold_seconds=1.0)
    hold.update(0.5, now=0.0)
    hold.update(0.9, now=0.9)
    hold.update(0.1, now=1.5)

    assert hold.peak == 0.9


def test_peak_hold_reset_forgets_the_peak() -> None:
    hold = PeakHold()
    hold.update(0.7, now=0.0)
    hold.reset()
    hold.update(0.1, now=0.1)

    assert hold.peak == 0.1
    assert not math.isnan(hold.peak)
