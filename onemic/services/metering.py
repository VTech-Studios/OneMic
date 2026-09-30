from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from ..domain.errors import AudioError
from ..domain.levels import PeakHold
from ..domain.waveform import Samples, WaveColumn, summarise
from ..ports import ByteStream, SignalTapFactory

CHANNELS = 2
FRAMES_PER_COLUMN = 1024
BYTES_PER_COLUMN = FRAMES_PER_COLUMN * CHANNELS * 4
HISTORY_COLUMNS = 480

log = logging.getLogger(__name__)


def decode(chunk: bytes) -> Samples:
    """Turn raw tap output into samples shaped (frames, channels).

    A read can end part-way through a frame when the tap stops, so any
    partial frame is dropped rather than misread as another channel.

    @param chunk: interleaved 32-bit float samples.
    @return: the whole frames in the chunk.
    """
    usable = len(chunk) - len(chunk) % (CHANNELS * 4)
    return np.frombuffer(chunk[:usable], dtype=np.float32).reshape(-1, CHANNELS)


@dataclass(frozen=True)
class MeterReading:
    columns: tuple[WaveColumn, ...]
    held_peak: float


EMPTY_READING = MeterReading((), 0.0)


class ChannelMeter:
    """The recent waveform and held peak of one signal.

    Samples arrive on a reader thread while the interface reads on its own,
    so every access goes through one lock, and readers get a copy.
    """

    def __init__(self, history: int = HISTORY_COLUMNS, clock: Callable[[], float] = time.monotonic) -> None:
        self._columns: deque[WaveColumn] = deque(maxlen=history)
        self._hold = PeakHold()
        self._clock = clock
        self._lock = threading.Lock()

    def push(self, block: Samples) -> None:
        """Add a block of samples as the newest waveform column.

        @param block: samples shaped (frames, channels).
        """
        column = summarise(block)
        with self._lock:
            self._columns.append(column)
            self._hold.update(column.peak, self._clock())

    def reading(self) -> MeterReading:
        """Copy the current waveform and held peak for drawing.

        @return: the columns, oldest first, and the held peak.
        """
        with self._lock:
            return MeterReading(tuple(self._columns), self._hold.peak)


class TapReader:
    """Feeds one tap's samples into its meter on a background thread.

    Reading blocks until audio arrives, which would freeze the interface,
    so each tap gets a daemon thread that ends when its stream closes.
    """

    def __init__(self, stream: ByteStream, meter: ChannelMeter) -> None:
        self._stream = stream
        self.meter = meter
        self._thread = threading.Thread(target=self._run, name="onemic-tap", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Stop the tap and wait for its thread to finish."""
        self._stream.close()
        self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while chunk := self._stream.read(BYTES_PER_COLUMN):
            self.meter.push(decode(chunk))


class Metering:
    """Keeps exactly the wanted taps running.

    Taps are keyed by input id, plus one for the mix, so a row's waveform
    history survives unrelated edits such as another input being removed.
    """

    def __init__(self, taps: SignalTapFactory, meters: Callable[[], ChannelMeter] = ChannelMeter) -> None:
        self._taps = taps
        self._meters = meters
        self._readers: dict[str, tuple[str, TapReader]] = {}

    def sync(self, wanted: Mapping[str, str]) -> None:
        """Open missing taps and close unwanted ones.

        @param wanted: tap node names, keyed by input id or the mix key.
        """
        for key in [key for key, (name, _) in self._readers.items() if wanted.get(key) != name]:
            self._readers.pop(key)[1].close()
        for key, name in wanted.items():
            if key not in self._readers:
                self._open(key, name)

    def readings(self) -> dict[str, MeterReading]:
        """Copy every meter's current state for drawing.

        @return: one reading per running tap, keyed like sync's argument.
        """
        return {key: reader.meter.reading() for key, (_, reader) in self._readers.items()}

    def close(self) -> None:
        """Stop every tap, as the window closes."""
        self.sync({})

    def _open(self, key: str, name: str) -> None:
        try:
            self._readers[key] = (name, TapReader(self._taps.open(name), self._meters()))
        except AudioError as error:
            log.warning("Meter for %s unavailable: %s", key, error)
