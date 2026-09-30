from __future__ import annotations

from ..ports import CommandRunner


class WpctlVolume:
    """Sets node volumes through WirePlumber's wpctl.

    wpctl uses the same volume scale as the desktop's own mixer, so 100%
    here sounds the same as 100% in the system tray.
    """

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def set_volume(self, node_id: int, gain: float) -> None:
        """Set a node's volume.

        @param node_id: the node's id in the current graph.
        @param gain: the new volume, where 1.0 is unity.
        """
        self._runner.run(["wpctl", "set-volume", str(node_id), f"{gain:.3f}"])

    def set_muted(self, node_id: int, muted: bool) -> None:
        """Mute or unmute a node.

        @param node_id: the node's id in the current graph.
        @param muted: True to silence the node.
        """
        self._runner.run(["wpctl", "set-mute", str(node_id), "1" if muted else "0"])
