from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..domain.levels import DISPLAY_FLOOR_DB, Level, LevelThresholds, db_to_fraction
from .theme import Palette

FLOOR_DB = DISPLAY_FLOOR_DB


def zones(level_db: float, thresholds: LevelThresholds) -> list[tuple[Level, float, float]]:
    """Split the lit part of the meter into its coloured zones.

    @param level_db: the level the meter shows, in dBFS.
    @param thresholds: where hot and clipping start.
    @return: each lit zone's level and its start and end as fractions of the width.
    """
    lit = db_to_fraction(level_db)
    edges = [
        (Level.SAFE, 0.0, db_to_fraction(thresholds.hot_db)),
        (Level.HOT, db_to_fraction(thresholds.hot_db), db_to_fraction(thresholds.clip_db)),
        (Level.CLIP, db_to_fraction(thresholds.clip_db), 1.0),
    ]
    return [(level, start, min(end, lit)) for level, start, end in edges if lit > start]


class LevelMeter(QWidget):
    """A thin horizontal level meter with a peak-hold tick, like a DAW track meter.

    It shows the signal right now, where the waveform shows its recent
    history, so it reacts the moment a sound starts.
    """

    def __init__(self, palette: Palette, thresholds: LevelThresholds, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._thresholds = thresholds
        self._level_db = FLOOR_DB
        self._hold_db = FLOOR_DB
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(4)

    def set_level(self, level_db: float, hold_db: float) -> None:
        """Show a new level.

        @param level_db: the current level in dBFS.
        @param hold_db: the held peak in dBFS, marked with a tick.
        """
        if (level_db, hold_db) != (self._level_db, self._hold_db):
            self._level_db, self._hold_db = level_db, hold_db
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        width, height = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(self._palette.border))
        for level, start, end in zones(self._level_db, self._thresholds):
            painter.fillRect(
                QRectF(start * width, 0, (end - start) * width, height), self._palette.level_colour(level)
            )
        if self._hold_db > FLOOR_DB:
            tick = db_to_fraction(self._hold_db) * width
            painter.fillRect(QRectF(min(tick, width - 2), 0, 2, height), QColor(self._palette.text))
        painter.end()
