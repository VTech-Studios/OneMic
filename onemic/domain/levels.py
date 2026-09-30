from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

SILENCE_DB = -120.0


class Level(Enum):
    SAFE = "safe"
    HOT = "hot"
    CLIP = "clip"


def amplitude_to_db(amplitude: float) -> float:
    """Convert a linear sample amplitude to decibels relative to full scale.

    Silence has no finite decibel value, so it is clamped to a floor that
    still compares and formats like any other reading.

    @param amplitude: absolute sample value, where 1.0 is full scale.
    @return: the level in dBFS, never lower than SILENCE_DB.
    """
    if amplitude <= 0.0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(amplitude))


DISPLAY_FLOOR_DB = -60.0


def db_to_fraction(db: float, floor_db: float = DISPLAY_FLOOR_DB) -> float:
    """Place a level on a display that is linear in decibels.

    Level meters use this scale, as DAW meters do, so the quiet half of the
    range stays readable instead of being squashed at the left.

    @param db: the level in dBFS.
    @param floor_db: the level shown as empty.
    @return: 0.0 at the floor to 1.0 at full scale, clamped.
    """
    return min(max((db - floor_db) / -floor_db, 0.0), 1.0)


@dataclass(frozen=True)
class LevelThresholds:
    """Where a signal stops being safe to send.

    A call has no headroom after the mic: the far end hears any clipping, and
    browsers add their own gain on top, so the warning starts well below
    0 dBFS rather than at it.
    """

    hot_db: float = -6.0
    clip_db: float = -0.1

    def classify(self, peak: float) -> Level:
        """Grade a peak so every view colours the same signal the same way.

        @param peak: absolute peak amplitude, where 1.0 is full scale.
        @return: CLIP at or above clip_db, HOT at or above hot_db, else SAFE.
        """
        db = amplitude_to_db(peak)
        if db >= self.clip_db:
            return Level.CLIP
        if db >= self.hot_db:
            return Level.HOT
        return Level.SAFE


@dataclass
class MeterBallistics:
    """How a level meter moves: straight up to a new peak, then a steady fall.

    Rising instantly is what makes a meter feel live, since it jumps the
    moment you play. Falling at a fixed rate in decibels, as a DAW's meters
    do, keeps it readable instead of flickering with every sample.
    """

    fall_db_per_second: float = 24.0
    floor_db: float = -60.0
    _level_db: float = field(default=-60.0, init=False)

    @property
    def level_db(self) -> float:
        return self._level_db

    def update(self, peak: float, elapsed: float) -> float:
        """Move the meter towards the latest peak.

        @param peak: absolute peak amplitude heard since the last update.
        @param elapsed: seconds since the last update.
        @return: the level to show, in dBFS, never below floor_db.
        """
        fallen = self._level_db - self.fall_db_per_second * max(elapsed, 0.0)
        self._level_db = max(amplitude_to_db(peak), fallen, self.floor_db)
        return self._level_db


@dataclass
class PeakHold:
    """Keeps the highest recent peak on screen long enough to be read.

    A live peak changes forty times a second, far too fast to read a number
    from, so the highest value is held for a moment before it may fall.
    """

    hold_seconds: float = 1.5
    _peak: float = field(default=0.0, init=False)
    _held_at: float = field(default=-math.inf, init=False)

    @property
    def peak(self) -> float:
        return self._peak

    def update(self, peak: float, now: float) -> None:
        """Offer a new peak, which replaces the held one if higher or if the hold expired.

        @param peak: absolute peak amplitude of the latest block.
        @param now: a monotonic time in seconds, passed in so tests control the clock.
        """
        if peak >= self._peak or now - self._held_at > self.hold_seconds:
            self._peak = peak
            self._held_at = now

    def reset(self) -> None:
        """Forget the held peak, so a stopped signal stops showing its last value."""
        self._peak = 0.0
        self._held_at = -math.inf
