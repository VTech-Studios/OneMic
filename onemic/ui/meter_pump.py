from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6.QtCore import QObject, QTimer

from ..domain.naming import MIX_TAP, NodeNames
from ..services.metering import Metering, MeterReading

FRAME_MS = 33


def wanted_taps(slug: str | None, input_ids: Sequence[str]) -> dict[str, str]:
    """Decide which signals to meter.

    Only rows on screen are metered, plus the mix, so a mic with eight
    inputs shown compactly runs three taps rather than nine.

    @param slug: the live mic's slug, or None when nothing is live.
    @param input_ids: the inputs whose rows are visible.
    @return: tap node names keyed by input id or the mix key; empty when not live.
    """
    if slug is None:
        return {}
    names = NodeNames(slug)
    taps = {input_id: names.tap(input_id) for input_id in input_ids}
    taps[MIX_TAP] = names.mix_tap
    return taps


class MeterPump(QObject):
    """Moves meter readings to the screen about thirty times a second."""

    def __init__(
        self,
        metering: Metering,
        draw: Callable[[Mapping[str, MeterReading]], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._metering = metering
        self._draw = draw
        self._timer = QTimer(self, interval=FRAME_MS)
        self._timer.timeout.connect(lambda: self._draw(self._metering.readings()))

    def follow(self, slug: str | None, input_ids: Sequence[str]) -> None:
        """Meter the given rows of the live mic, or nothing if none is live.

        @param slug: the live mic's slug, or None.
        @param input_ids: the inputs whose rows are visible.
        """
        taps = wanted_taps(slug, input_ids)
        self._metering.sync(taps)
        if taps:
            self._timer.start()
        else:
            self._timer.stop()

    def close(self) -> None:
        """Stop drawing and close every tap."""
        self._timer.stop()
        self._metering.close()
