from __future__ import annotations

from dataclasses import dataclass

from .profile import InputSettings

STAGE_PROGRAM = "pipewire"
STAGE_MARKER = "/onemic/stages/"
LOW_CUT_HZ = 100.0
BYPASS_HZ = 5.0


def db_to_amplitude(db: float) -> float:
    """Convert decibels relative to full scale to a linear amplitude.

    @param db: the level in dBFS.
    @return: the amplitude, where 1.0 is full scale.
    """
    return float(10 ** (db / 20))


@dataclass(frozen=True)
class StageControls:
    """The values sent to one gain stage's filter chain.

    Every control is always present, so switching a filter off is just a
    change of value, never a rebuild of the chain that would interrupt the
    audio. A low-cut at 5 Hz passes everything audible, and a disabled gate
    passes its input untouched.
    """

    low_cut_hz: float
    multiplier: float
    gate_on: bool
    gate_threshold: float


def stage_controls(settings: InputSettings, silenced: bool) -> StageControls:
    """Work out one input's filter chain values from its settings.

    The gain is cubed, matching the desktop's volume scale, so 50% on a
    OneMic slider sounds like 50% on the system volume.

    @param settings: the input.
    @param silenced: True if mute or another input's solo silences it.
    @return: the values to send.
    """
    return StageControls(
        low_cut_hz=LOW_CUT_HZ if settings.low_cut else BYPASS_HZ,
        multiplier=0.0 if silenced else settings.gain**3,
        gate_on=settings.gate,
        gate_threshold=db_to_amplitude(settings.gate_threshold_db),
    )
