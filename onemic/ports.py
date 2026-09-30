from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .domain.graph import Graph, Link
from .domain.profile import MicProfile
from .domain.stage import StageControls
from .domain.window import WindowState


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], timeout: float = 5.0) -> str:
        """Run a command to completion.

        @param args: the program and its arguments, never passed through a shell.
        @param timeout: seconds before the command is abandoned.
        @return: the command's standard output.
        @raise AudioError: if the command is missing, times out, or fails.
        """
        ...


class ByteStream(Protocol):
    def read(self, size: int) -> bytes:
        """Block until a chunk of output arrives.

        @param size: the number of bytes wanted.
        @return: up to size bytes, or an empty result once the stream has ended.
        """
        ...

    def close(self) -> None:
        """Stop the producer and release the stream."""
        ...


class ProcessLauncher(Protocol):
    def spawn_detached(self, args: Sequence[str]) -> int:
        """Start a long-lived helper that outlives this application.

        @param args: the program and its arguments.
        @return: the new process id.
        @raise AudioError: if the program cannot be started.
        """
        ...

    def open_stream(self, args: Sequence[str]) -> ByteStream:
        """Start a helper whose standard output is read continuously.

        @param args: the program and its arguments.
        @return: a stream over the helper's standard output.
        @raise AudioError: if the program cannot be started.
        """
        ...

    def terminate(self, pid: int, program: str, marker: str) -> None:
        """Ask a process to stop, but only if it is one of OneMic's own helpers.

        @param pid: the process id.
        @param program: the executable the process must be running.
        @param marker: text its command line must contain.
        """
        ...


class AudioGraph(Protocol):
    def snapshot(self) -> Graph:
        """Read the whole audio graph at once.

        @return: every audio node, port and link, plus the default output.
        @raise AudioError: if the graph cannot be read.
        """
        ...

    def link(self, link: Link) -> None:
        """Connect an output port to an input port.

        @param link: the port ids to join.
        @raise AudioError: if PipeWire refuses the link.
        """
        ...

    def unlink(self, link: Link) -> None:
        """Disconnect an output port from an input port.

        @param link: the port ids to separate.
        @raise AudioError: if PipeWire refuses to remove the link.
        """
        ...


class VirtualMicDriver(Protocol):
    def create(self, node_name: str, description: str) -> None:
        """Create the device that call applications list as a microphone.

        @param node_name: the stable node name.
        @param description: the name shown in device lists.
        """
        ...

    def remove(self, node_name: str) -> None:
        """Remove the device, which call applications then see as unplugged.

        @param node_name: the stable node name given to create.
        """
        ...


class VolumeControl(Protocol):
    def set_volume(self, node_id: int, gain: float) -> None:
        """Set a node's volume.

        @param node_id: the node's id in the current graph.
        @param gain: the new volume, where 1.0 is unity.
        """
        ...

    def set_muted(self, node_id: int, muted: bool) -> None:
        """Mute or unmute a node.

        @param node_id: the node's id in the current graph.
        @param muted: True to silence the node.
        """
        ...


class GainStageDriver(Protocol):
    def start(self, capture_name: str, playback_name: str, description: str, controls: StageControls) -> None:
        """Start a gain stage: a node pair that processes a source on its way to a mic.

        @param capture_name: node name for the side that receives the source.
        @param playback_name: node name for the side that feeds the mic.
        @param description: the name shown in patchbays such as qpwgraph.
        @param controls: the stage's starting low-cut, gain and gate values.
        """
        ...


class StageControl(Protocol):
    def set_controls(self, node_id: int, controls: StageControls) -> None:
        """Change a running stage's low-cut, gain and gate.

        @param node_id: the id of the stage's capture node.
        @param controls: the values to send.
        """
        ...


class SignalTapFactory(Protocol):
    def open(self, node_name: str) -> ByteStream:
        """Start a recording node whose samples arrive as a byte stream.

        @param node_name: the tap node's name, which the session links to a signal.
        @return: 32-bit float stereo samples at the tap's rate.
        """
        ...


class ProfileStore(Protocol):
    def load(self) -> tuple[list[MicProfile], str | None]:
        """Read every saved mic.

        @return: the mics, and the slug of the one last selected.
        """
        ...

    def save(self, profiles: Sequence[MicProfile], selected: str | None) -> None:
        """Replace the saved mics.

        @param profiles: every mic, in display order.
        @param selected: the slug of the mic to reopen next time.
        """
        ...


class WindowStateStore(Protocol):
    def load(self) -> WindowState:
        """Read where the window was left.

        @return: the saved state, or the defaults if none was saved.
        """
        ...

    def save(self, state: WindowState) -> None:
        """Remember where the window is.

        @param state: the window's corner, screen and size.
        """
        ...
