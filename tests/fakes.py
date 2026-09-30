from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import replace

from onemic.domain.errors import AudioError
from onemic.domain.graph import Graph, Link, Node, Port
from onemic.domain.profile import MicProfile
from onemic.domain.stage import STAGE_MARKER, STAGE_PROGRAM, StageControls
from onemic.domain.window import WindowState


class FakePipeWire:
    """An in-memory audio graph that behaves like PipeWire for the session.

    Creating a mic or a gain stage adds nodes with ports, stopping a stage's
    process removes its nodes, and links are recorded. It implements every
    port the session uses, so session tests read like real use.
    """

    def __init__(self, default_sink: str | None = None) -> None:
        self._ids = itertools.count(100)
        self._pids = itertools.count(5000)
        self.nodes: list[Node] = []
        self.links: set[Link] = set()
        self.default_sink = default_sink
        self.volumes: dict[int, float] = {}
        self.mutes: dict[int, bool] = {}
        self.volume_calls = 0
        self.terminated: list[int] = []
        self.created_mics: list[tuple[str, str]] = []
        self.started_stages: list[tuple[str, str, str]] = []
        self.stage_controls: dict[int, StageControls] = {}
        self.started_controls: dict[str, StageControls] = {}
        self.refuse_links_into: set[str] = set()
        self.refuse_mic = False
        self.refuse_snapshots = False
        self.refuse_volumes = False
        self.hidden_ports_for = 0

    def add_node(
        self, name: str, media_class: str, inputs: int = 0, outputs: int = 0, process_id: int | None = None
    ) -> Node:
        node_id = next(self._ids)
        node = Node(
            id=node_id,
            name=name,
            description=name,
            media_class=media_class,
            inputs=self._ports("in", inputs),
            outputs=self._ports("out", outputs),
            process_id=process_id,
            serial=node_id,
        )
        self.nodes.append(node)
        return node

    def remove_node(self, name: str) -> None:
        self._discard(self.node(name))

    def _discard(self, node: Node) -> None:
        ports = {port.id for port in (*node.inputs, *node.outputs)}
        self.nodes.remove(node)
        self.links = {link for link in self.links if not {link.output_port, link.input_port} & ports}

    def node(self, name: str) -> Node:
        found = next((node for node in self.nodes if node.name == name), None)
        assert found is not None, f"no node {name}"
        return found

    def has_node(self, name: str) -> bool:
        return any(node.name == name for node in self.nodes)

    def linked(self, source: str, destination: str) -> bool:
        outputs = {port.id for port in self.node(source).outputs}
        inputs = {port.id for port in self.node(destination).inputs}
        return any(link.output_port in outputs and link.input_port in inputs for link in self.links)

    def snapshot(self) -> Graph:
        if self.refuse_snapshots:
            raise AudioError("pw-dump did not answer")
        if self.hidden_ports_for:
            self.hidden_ports_for -= 1
            nodes = tuple(replace(node, inputs=(), outputs=()) for node in self.nodes)
            return Graph(nodes, frozenset(self.links), self.default_sink)
        return Graph(tuple(self.nodes), frozenset(self.links), self.default_sink)

    def link(self, link: Link) -> None:
        refused = {port.id for name in self.refuse_links_into for port in self.node(name).inputs}
        if link.input_port in refused:
            raise AudioError("port vanished")
        self.links.add(link)

    def unlink(self, link: Link) -> None:
        self.links.discard(link)

    def create(self, node_name: str, description: str) -> None:
        if self.refuse_mic:
            raise AudioError("Module initialization failed")
        self.created_mics.append((node_name, description))
        self.add_node(node_name, "Audio/Source/Virtual", inputs=2, outputs=2, process_id=1)

    def remove(self, node_name: str) -> None:
        if self.has_node(node_name):
            self.remove_node(node_name)

    def start(self, capture_name: str, playback_name: str, description: str, controls: StageControls) -> None:
        self.started_stages.append((capture_name, playback_name, description))
        self.started_controls[capture_name] = controls
        pid = next(self._pids)
        self.add_node(capture_name, "Stream/Input/Audio", inputs=2, outputs=2, process_id=pid)
        self.add_node(playback_name, "Stream/Output/Audio", outputs=2, process_id=pid)

    def set_volume(self, node_id: int, gain: float) -> None:
        if self.refuse_volumes:
            raise AudioError("wpctl: node not found")
        self.volume_calls += 1
        self.volumes[node_id] = gain

    def set_muted(self, node_id: int, muted: bool) -> None:
        self.mutes[node_id] = muted

    def set_controls(self, node_id: int, controls: StageControls) -> None:
        if self.refuse_volumes:
            raise AudioError("pw-cli: node not found")
        self.stage_controls[node_id] = controls

    def terminate(self, pid: int, program: str, marker: str) -> None:
        assert (program, marker) == (STAGE_PROGRAM, STAGE_MARKER)
        self.terminated.append(pid)
        for node in [node for node in self.nodes if node.process_id == pid]:
            self._discard(node)

    def spawn_detached(self, args: Sequence[str]) -> int:
        raise NotImplementedError

    def open_stream(self, args: Sequence[str]) -> FakeStream:
        raise NotImplementedError

    def _ports(self, direction: str, count: int) -> tuple[Port, ...]:
        channels = ["MONO"] if count == 1 else ["FL", "FR", "RL", "RR"][:count]
        prefix = "input" if direction == "in" else "output"
        return tuple(Port(next(self._ids), f"{prefix}_{channel}", channel) for channel in channels)


class FakeRunner:
    """CommandRunner that records calls and answers from a list of rules.

    Each rule pairs an argument prefix with a response. A response that is
    an exception is raised instead of returned.
    """

    def __init__(self, rules: Iterable[tuple[Sequence[str], str | Exception]] = ()) -> None:
        self.calls: list[list[str]] = []
        self._rules = [(list(prefix), response) for prefix, response in rules]

    def run(self, args: Sequence[str], timeout: float = 5.0) -> str:
        call = list(args)
        self.calls.append(call)
        for prefix, response in self._rules:
            if call[: len(prefix)] == prefix:
                if isinstance(response, Exception):
                    raise response
                return response
        return ""


class FakeStream:
    """A byte stream that yields prepared chunks, then ends."""

    def __init__(self, chunks: Iterable[bytes] = ()) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def read(self, size: int) -> bytes:
        return self._chunks.pop(0) if self._chunks and not self.closed else b""

    def close(self) -> None:
        self.closed = True


class FakeLauncher:
    """ProcessLauncher that records what would have been started."""

    def __init__(self, stream: FakeStream | None = None) -> None:
        self.spawned: list[list[str]] = []
        self.streams: list[list[str]] = []
        self.terminated: list[tuple[int, str, str]] = []
        self._stream = stream or FakeStream()

    def spawn_detached(self, args: Sequence[str]) -> int:
        self.spawned.append(list(args))
        return 4242

    def open_stream(self, args: Sequence[str]) -> FakeStream:
        self.streams.append(list(args))
        return self._stream

    def terminate(self, pid: int, program: str, marker: str) -> None:
        self.terminated.append((pid, program, marker))


class FakeTaps:
    """SignalTapFactory handing out FakeStreams and recording which taps were opened."""

    def __init__(self, failing: Iterable[str] = ()) -> None:
        self.opened: dict[str, FakeStream] = {}
        self._failing = set(failing)

    def open(self, node_name: str) -> FakeStream:
        if node_name in self._failing:
            raise AudioError("pw-record could not be started")
        stream = FakeStream()
        self.opened[node_name] = stream
        return stream


class InMemoryProfileStore:
    def __init__(self, profiles: Sequence[MicProfile] = (), selected: str | None = None) -> None:
        self.profiles = list(profiles)
        self.selected = selected
        self.saves = 0

    def load(self) -> tuple[list[MicProfile], str | None]:
        return list(self.profiles), self.selected

    def save(self, profiles: Sequence[MicProfile], selected: str | None) -> None:
        self.profiles = list(profiles)
        self.selected = selected
        self.saves += 1


class InMemoryWindowStore:
    def __init__(self, state: WindowState | None = None) -> None:
        self.state = state or WindowState()
        self.saved: list[WindowState] = []

    def load(self) -> WindowState:
        return self.state

    def save(self, state: WindowState) -> None:
        self.state = state
        self.saved.append(state)
