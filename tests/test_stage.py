import pytest

from onemic.domain.profile import InputSettings
from onemic.domain.stage import BYPASS_HZ, LOW_CUT_HZ, db_to_amplitude, stage_controls

PLAIN = InputSettings("a", "s", "Voice", gain=0.5)


def test_a_plain_input_bypasses_its_filters_and_cubes_its_gain() -> None:
    controls = stage_controls(PLAIN, silenced=False)

    assert controls.low_cut_hz == BYPASS_HZ
    assert controls.multiplier == pytest.approx(0.125)
    assert not controls.gate_on


def test_a_silenced_input_is_multiplied_to_nothing() -> None:
    assert stage_controls(PLAIN, silenced=True).multiplier == 0.0


def test_filters_follow_the_settings() -> None:
    settings = InputSettings("a", "s", "Voice", low_cut=True, gate=True, gate_threshold_db=-40.0)

    controls = stage_controls(settings, silenced=False)

    assert controls.low_cut_hz == LOW_CUT_HZ
    assert controls.gate_on
    assert controls.gate_threshold == pytest.approx(0.01)


def test_db_to_amplitude() -> None:
    assert db_to_amplitude(0.0) == 1.0
    assert db_to_amplitude(-20.0) == pytest.approx(0.1)
