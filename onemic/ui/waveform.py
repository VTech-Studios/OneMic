from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from PySide6.QtCore import QLineF, QSize
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..domain.levels import Level, LevelThresholds
from ..domain.waveform import WaveColumn
from .theme import Palette


def column_lines(
    columns: Sequence[WaveColumn], width: int, height: int, thresholds: LevelThresholds
) -> dict[Level, list[QLineF]]:
    """Turn waveform columns into vertical lines, grouped by colour.

    The newest column sits at the right edge and older ones scroll left,
    one pixel each, like a DAW's recording lane. Grouping by level lets the
    painter draw each colour in one call, so a clip shows red exactly where
    it happened while the rest stays ice blue.

    @param columns: waveform columns, oldest first.
    @param width: the drawing width in pixels.
    @param height: the drawing height in pixels.
    @param thresholds: where hot and clipping start.
    @return: the lines to draw, keyed by level.
    """
    middle = height / 2
    visible = list(columns)[-width:] if width > 0 else []
    offset = width - len(visible)
    lines: dict[Level, list[QLineF]] = defaultdict(list)
    for index, column in enumerate(visible):
        x = offset + index + 0.5
        top = middle - min(column.high, 1.0) * middle
        bottom = middle - max(column.low, -1.0) * middle
        lines[thresholds.classify(column.peak)].append(QLineF(x, top, x, max(bottom, top + 1)))
    return lines


class WaveformView(QWidget):
    """A small scrolling waveform for one signal."""

    def __init__(self, palette: Palette, thresholds: LevelThresholds, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette
        self._thresholds = thresholds
        self._columns: Sequence[WaveColumn] = ()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(28)

    def sizeHint(self) -> QSize:
        return QSize(260, self.height())

    def set_columns(self, columns: Sequence[WaveColumn]) -> None:
        """Show new waveform data.

        @param columns: waveform columns, oldest first; empty for no signal.
        """
        self._columns = columns
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(self._palette.background))
        painter.setPen(QPen(QColor(self._palette.border), 1))
        painter.drawLine(0, self.height() // 2, self.width(), self.height() // 2)
        for level, lines in column_lines(
            self._columns, self.width(), self.height(), self._thresholds
        ).items():
            painter.setPen(QPen(self._palette.level_colour(level), 1))
            painter.drawLines(lines)
        painter.end()
