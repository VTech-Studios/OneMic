from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6.QtCore import QObject, QTimer

from ..domain.naming import MIX_TAP, NodeNames
from ..services.metering import MeterReading, MeterSource

FRAME_MS = 16


def wanted_taps(slug: str, input_ids: Sequence[str], live: bool) -> dict[str, str]:
    """Decide which signals to meter.

    Only rows on screen are metered, so a mic with eight inputs shown
    compactly runs three taps rather than nine. The mix only exists while
    the mic is live, so it is only metered then.

    @param slug: the slug of the mic on screen.
    @param input_ids: the inputs whose rows are visible.
    @param live: True while that mic is live.
    @return: tap node names keyed by input id or the mix key.
    """
    names = NodeNames(slug)
    taps = {input_id: names.tap(input_id) for input_id in input_ids}
    if live:
        taps[MIX_TAP] = names.mix_tap
    return taps


class MeterPump(QObject):
    """Moves meter readings to the screen about thirty times a second."""

    def __init__(
        self,
        metering: MeterSource,
        draw: Callable[[Mapping[str, MeterReading]], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._metering = metering
        self._draw = draw
        self._timer = QTimer(self, interval=FRAME_MS)
        self._timer.timeout.connect(lambda: self._draw(self._metering.readings()))

    def follow(self, slug: str, input_ids: Sequence[str], live: bool) -> None:
        """Meter the visible rows of the mic on screen.

        @param slug: the slug of the mic on screen.
        @param input_ids: the inputs whose rows are visible.
        @param live: True while that mic is live, which adds the mix.
        """
        taps = wanted_taps(slug, input_ids, live)
        self._metering.sync(taps)
        if not taps:
            self._timer.stop()
            self._draw({})
        elif not self._timer.isActive():
            self._timer.start()

    def close(self) -> None:
        """Stop drawing and close every tap."""
        self._timer.stop()
        self._metering.close()
