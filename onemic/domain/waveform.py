from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import numpy.typing as npt

from .levels import display_height

Samples = npt.NDArray[np.float32]


@dataclass(frozen=True)
class WaveColumn:
    """One vertical slice of a scrolling waveform.

    Drawing every sample would need thousands of pixels a second, so each
    block of audio is reduced to its lowest and highest sample, which is
    exactly what a waveform shows at this zoom level. The time lets the view
    place it by when it happened rather than by when it was drawn, which is
    what makes the scrolling smooth.
    """

    low: float
    high: float
    at: float = 0.0

    @cached_property
    def peak(self) -> float:
        return max(abs(self.low), abs(self.high))

    @cached_property
    def display(self) -> tuple[float, float]:
        """Work out where the column is drawn, once, since a column never changes.

        Every frame redraws every visible column, and recalculating
        decibels for each one sixty times a second is most of the cost of
        drawing.

        @return: the low and high edges on the decibel display scale.
        """
        return display_height(self.low), display_height(self.high)


SILENT_COLUMN = WaveColumn(0.0, 0.0)


def summarise(block: Samples, at: float = 0.0) -> WaveColumn:
    """Reduce a block of interleaved-channel audio to one waveform column.

    Both channels are folded together because the view shows one waveform
    per signal, and a clip on either channel must still show as a clip.

    @param block: samples shaped (frames, channels), or an empty array.
    @param at: when the block was heard, in monotonic seconds.
    @return: the block's lowest and highest sample across every channel.
    """
    if block.size == 0:
        return WaveColumn(0.0, 0.0, at)
    return WaveColumn(float(block.min()), float(block.max()), at)


def split_columns(chunk: Samples, frames_per_column: int, arrived: float, rate: int) -> list[WaveColumn]:
    """Cut a chunk of audio into columns, each stamped with when it was heard.

    A chunk arrives all at once but covers a stretch of time. Its last
    column is stamped with the arrival time and earlier ones step back by
    their duration, so columns are evenly spaced even though chunks are not.

    @param chunk: samples shaped (frames, channels).
    @param frames_per_column: how many frames make one column.
    @param arrived: when the chunk arrived, in monotonic seconds.
    @param rate: the sample rate, to turn frames into seconds.
    @return: the columns, oldest first.
    """
    count = max(len(chunk) // frames_per_column, 1)
    step = frames_per_column / rate
    return [
        summarise(
            chunk[index * frames_per_column : (index + 1) * frames_per_column],
            arrived - (count - 1 - index) * step,
        )
        for index in range(count)
    ]
