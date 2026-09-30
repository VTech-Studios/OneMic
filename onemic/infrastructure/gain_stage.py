from __future__ import annotations

import json

from ..ports import ProcessLauncher


def node_properties(name: str, description: str) -> str:
    """Build the properties for a node OneMic links by hand.

    Autoconnect is switched off, or WirePlumber would link the node to the
    default devices on its own, sending a mic straight to the speakers.
    The result is JSON, which PipeWire accepts, so any character in the
    description is safely quoted.

    @param name: the node name.
    @param description: the name shown in patchbays.
    @return: the properties as a JSON object.
    """
    return json.dumps({"node.name": name, "node.description": description, "node.autoconnect": False})


class PwLoopbackStages:
    """Runs each gain stage as a pw-loopback process.

    A link has no volume of its own. A loopback puts a stream between the
    source and the mic, and a stream has a volume and a mute, so each input
    can be set without touching the source itself, which would also change
    it for every other application, such as a DAW recording the same mic.
    """

    def __init__(self, launcher: ProcessLauncher) -> None:
        self._launcher = launcher

    def start(self, capture_name: str, playback_name: str, description: str) -> None:
        """Start a gain stage that keeps running if the window is closed.

        @param capture_name: node name for the side that receives the source.
        @param playback_name: node name for the side that feeds the mic.
        @param description: the name shown in patchbays such as qpwgraph.
        """
        self._launcher.spawn_detached(
            [
                "pw-loopback",
                "--channels",
                "2",
                "--capture-props",
                node_properties(capture_name, description),
                "--playback-props",
                node_properties(playback_name, f"{description} (out)"),
            ]
        )
