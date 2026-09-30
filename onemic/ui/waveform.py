from __future__ import annotations

import bisect
import time
from collections.abc import Callable, Sequence
from itertools import groupby

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..domain.levels import Level, LevelThresholds
from ..domain.waveform import WaveColumn
from .theme import Palette

PIXELS_PER_SECOND = 60.0
DISPLAY_DELAY = 0.04
HEADROOM = 0.92

Placed = tuple[float, WaveColumn]


def place(columns: Sequence[WaveColumn], width: int, now: float, speed: float) -> list[Placed]:
    """Position columns by when they were heard, so the waveform glides at a constant speed.

    The newest audio enters at the right edge and moves left at a fixed
    number of pixels per second. Positions are fractional, so with
    antialiasing the movement is smooth rather than stepping a pixel at a time.

    @param columns: waveform columns, oldest first.
    @param width: the drawing width in pixels.
    @param now: the moment being drawn, in monotonic seconds.
    @param speed: how far audio scrolls each second, in pixels.
    @return: each visible column with its x position, oldest first.
    """
    oldest = now - (width + 2.0) / speed
    first = bisect.bisect_left(columns, oldest, key=lambda column: column.at)
    placed = [(width - (now - column.at) * speed, column) for column in columns[first:]]
    return [(x, column) for x, column in placed if x <= width + 2.0]


def _outline(run: Sequence[Placed], middle: float) -> QPolygonF:
    """Trace the shape of a run of columns: along the highs, then back along the lows.

    Heights are linear, as in a DAW's recording lane, so the shape shows
    the real signal and the level meter below shows how loud it is.

    @param run: placed columns, left to right.
    @param middle: the y position of silence.
    @return: a closed shape, at least one pixel tall so silence still shows.
    """
    scale = middle * HEADROOM
    tops = [QPointF(x, middle - column.display[1] * scale - 0.5) for x, column in run]
    bottoms = [QPointF(x, middle - column.display[0] * scale + 0.5) for x, column in reversed(run)]
    return QPolygonF([*tops, *bottoms])


def waveform_shapes(
    placed: Sequence[Placed], height: int, thresholds: LevelThresholds
) -> list[tuple[Level, QPolygonF]]:
    """Group placed columns into filled shapes, one per stretch at the same level.

    Each stretch borrows the first column of the next, so neighbouring
    shapes meet with no gap and a clip shows red exactly where it happened.

    @param placed: columns with x positions, oldest first.
    @param height: the drawing height in pixels.
    @param thresholds: where hot and clipping start.
    @return: shapes with the level that colours them.
    """
    runs = [
        (level, list(run))
        for level, run in groupby(placed, key=lambda item: thresholds.classify(item[1].peak))
    ]
    shapes = []
    for index, (level, run) in enumerate(runs):
        following = runs[index + 1][1][:1] if index + 1 < len(runs) else [(run[-1][0] + 1.0, run[-1][1])]
        shapes.append((level, _outline(run + following, height / 2)))
    return shapes


class WaveformView(QWidget):
    """A small scrolling waveform for one signal, drawn like a DAW's recording lane.

    Drawing lags the newest audio by a few tens of milliseconds, so audio
    that arrives in chunks still slides in smoothly from the right edge
    instead of popping in a chunk at a time.
    """

    def __init__(
        self,
        palette: Palette,
        thresholds: LevelThresholds,
        parent: QWidget | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._thresholds = thresholds
        self._clock = clock
        self._columns: Sequence[WaveColumn] = ()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(30)

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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        placed = place(self._columns, self.width(), self._clock() - DISPLAY_DELAY, PIXELS_PER_SECOND)
        for level, shape in waveform_shapes(placed, self.height(), self._thresholds):
            painter.setBrush(self._palette.level_colour(level))
            painter.drawPolygon(shape)
        painter.end()
