from __future__ import annotations

from ..ports import ByteStream, ProcessLauncher
from .gain_stage import node_properties

TAP_RATE = 48000
TAP_CHANNELS = 2
TAP_LATENCY = "20ms"


class PwRecordTaps:
    """Opens metering taps as pw-record processes writing raw samples to a pipe.

    Tapping a signal is only another link in the graph, so metering never
    changes what the mic sends, and a tap that fails cannot silence a call.
    """

    def __init__(self, launcher: ProcessLauncher) -> None:
        self._launcher = launcher

    def open(self, node_name: str) -> ByteStream:
        """Start a recording node that the session links to the signal being metered.

        @param node_name: the tap node's name.
        @return: interleaved 32-bit float stereo samples at TAP_RATE.
        """
        return self._launcher.open_stream(
            [
                "pw-record",
                "--raw",
                "--format",
                "f32",
                "--rate",
                str(TAP_RATE),
                "--channels",
                str(TAP_CHANNELS),
                "--latency",
                TAP_LATENCY,
                "--target",
                "0",
                "--properties",
                node_properties(node_name, "OneMic meter"),
                "-",
            ]
        )
