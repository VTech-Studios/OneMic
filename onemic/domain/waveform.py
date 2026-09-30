from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Samples = npt.NDArray[np.float32]


@dataclass(frozen=True)
class WaveColumn:
    """One vertical slice of a scrolling waveform.

    Drawing every sample would need thousands of pixels a second, so each
    block of audio is reduced to its lowest and highest sample, which is
    exactly what a waveform shows at this zoom level.
    """

    low: float
    high: float

    @property
    def peak(self) -> float:
        return max(abs(self.low), abs(self.high))


SILENT_COLUMN = WaveColumn(0.0, 0.0)


def summarise(block: Samples) -> WaveColumn:
    """Reduce a block of interleaved-channel audio to one waveform column.

    Both channels are folded together because the view shows one waveform
    per signal, and a clip on either channel must still show as a clip.

    @param block: samples shaped (frames, channels), or an empty array.
    @return: the block's lowest and highest sample across every channel.
    """
    if block.size == 0:
        return SILENT_COLUMN
    return WaveColumn(float(block.min()), float(block.max()))
