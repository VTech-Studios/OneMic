from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..domain.levels import DISPLAY_FLOOR_DB, Level, LevelThresholds, db_to_fraction
from ..domain.profile import clamp_gate
from .theme import Palette

FLOOR_DB = DISPLAY_FLOOR_DB


def fraction_to_db(fraction: float, floor_db: float = FLOOR_DB) -> float:
    """Read a level off the meter from a position along it.

    @param fraction: 0.0 at the left edge to 1.0 at the right.
    @param floor_db: the level at the meter's left edge.
    @return: the level in dBFS at that position.
    """
    return floor_db + min(max(fraction, 0.0), 1.0) * -floor_db


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
    history, so it reacts the moment a sound starts. When the input's gate
    is on, its threshold is marked on the same scale and can be dragged, so
    it is set by eye against the room noise the meter is showing.
    """

    threshold_changed = Signal(float)

    def __init__(self, palette: Palette, thresholds: LevelThresholds, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._thresholds = thresholds
        self._level_db = FLOOR_DB
        self._hold_db = FLOOR_DB
        self._gate_db: float | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(10)

    def set_gate(self, threshold_db: float | None) -> None:
        """Show or hide the gate threshold marker.

        @param threshold_db: the threshold in dBFS, or None when the gate is off.
        """
        self._gate_db = threshold_db
        self.setCursor(
            Qt.CursorShape.SizeHorCursor if threshold_db is not None else Qt.CursorShape.ArrowCursor
        )
        self.setToolTip(
            f"Gate opens at {threshold_db:.0f} dB. Drag to move it." if threshold_db is not None else ""
        )
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._drag_to(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._drag_to(event)

    def _drag_to(self, event: QMouseEvent) -> None:
        """Move the gate threshold to where the pointer is.

        @param event: the press or drag, whose position picks the new threshold.
        """
        if self._gate_db is None or self.width() == 0:
            return
        threshold = clamp_gate(round(fraction_to_db(event.position().x() / self.width())))
        self.set_gate(threshold)
        QToolTip.showText(event.globalPosition().toPoint(), f"Gate {threshold:.0f} dB", self)
        self.threshold_changed.emit(threshold)

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
        width, bar_top, bar_height = self.width(), (self.height() - 4) / 2, 4.0
        painter.fillRect(QRectF(0, bar_top, width, bar_height), QColor(self._palette.border))
        for level, start, end in zones(self._level_db, self._thresholds):
            lit = QRectF(start * width, bar_top, (end - start) * width, bar_height)
            painter.fillRect(lit, self._palette.level_colour(level))
        if self._hold_db > FLOOR_DB:
            tick = db_to_fraction(self._hold_db) * width
            painter.fillRect(QRectF(min(tick, width - 2), bar_top, 2, bar_height), QColor(self._palette.text))
        if self._gate_db is not None:
            marker = db_to_fraction(self._gate_db) * width
            painter.fillRect(QRectF(min(marker, width - 2), 0, 2, self.height()), QColor(self._palette.gate))
        painter.end()
