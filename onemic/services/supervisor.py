from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..domain.graph import Graph, Node
from ..domain.naming import NodeNames, is_onemic_node, is_tap, mic_slug
from ..domain.profile import InputSettings, MicProfile
from ..ports import AudioGraph, GainStageDriver, ProcessLauncher, VirtualMicDriver

STAGE_PROGRAM = "pw-loopback"


@dataclass(frozen=True)
class Timing:
    """How long to wait for nodes that were just started.

    Nodes appear a moment after their process starts. Waiting briefly lets
    the first pass link everything, instead of leaving the mic silent until
    the next pass. The grace period stops a slow start from being mistaken
    for a missing node and started a second time.
    """

    attempts: int = 20
    interval: float = 0.05
    grace: float = 5.0


class NodeSupervisor:
    """Keeps exactly one of each node a live mic needs, and nothing else.

    Starts the mic and its gain stages when missing, stops stages that are
    stale or duplicated, and takes everything down on request. The session
    decides what should exist. This class makes it so.
    """

    def __init__(
        self,
        *,
        graph: AudioGraph,
        mics: VirtualMicDriver,
        stages: GainStageDriver,
        launcher: ProcessLauncher,
        timing: Timing | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._graph = graph
        self._mics = mics
        self._stages = stages
        self._launcher = launcher
        self._timing = timing or Timing()
        self._sleep = sleep
        self._clock = clock
        self._started: dict[str, float] = {}

    def ensure(self, profile: MicProfile, graph: Graph) -> Graph:
        """Bring the mic's nodes into existence and remove any that should not exist.

        @param profile: the live mic.
        @param graph: the current snapshot.
        @return: a snapshot in which new nodes have had time to publish their ports.
        """
        names = NodeNames(profile.slug)
        self._stop_duplicates(names, graph)
        self._stop_stale(profile, names, graph)
        wanted = [self._ensure_mic(profile, names, graph)]
        for settings in profile.inputs:
            wanted += self._ensure_stage(profile, settings, names, graph)
        missing = [name for name in wanted if not self._ready(graph, name)]
        return self._await(missing) if missing else graph

    def teardown(self, graph: Graph, keep: NodeNames | None) -> None:
        """Remove every OneMic mic and gain stage except those of one mic.

        Taps are left alone, because they belong to the running window and
        are closed by it.

        @param graph: the current snapshot.
        @param keep: the mic to spare, or None to remove everything.
        """
        doomed = [
            node
            for node in graph.nodes
            if is_onemic_node(node.name) and not is_tap(node.name) and not (keep and keep.owns(node.name))
        ]
        for name in {node.name for node in doomed if mic_slug(node.name) is not None}:
            self._mics.remove(name)
        self._terminate(node for node in doomed if mic_slug(node.name) is None)
        for node in doomed:
            self._started.pop(node.name, None)

    def _ensure_mic(self, profile: MicProfile, names: NodeNames, graph: Graph) -> str:
        if graph.node(names.mic) is None and not self._starting(names.mic):
            self._mics.create(names.mic, f"{profile.name} (OneMic)")
            self._started[names.mic] = self._clock()
        return names.mic

    def _ensure_stage(
        self, profile: MicProfile, settings: InputSettings, names: NodeNames, graph: Graph
    ) -> list[str]:
        """Start an input's gain stage if either half of it is missing.

        A stage whose other half is still running is stopped first, because
        pw-loopback cannot recreate one half on its own.

        @param profile: the live mic.
        @param settings: the input the stage belongs to.
        @param names: the mic's node names.
        @param graph: the current snapshot.
        @return: the stage's two node names.
        """
        pair = [names.stage_input(settings.id), names.stage_output(settings.id)]
        if any(graph.node(name) is None for name in pair) and not self._starting(pair[0]):
            self._terminate(graph.node(name) for name in pair)
            self._stages.start(pair[0], pair[1], f"OneMic {profile.name}: {settings.label}")
            self._started[pair[0]] = self._clock()
        return pair

    def _starting(self, name: str) -> bool:
        """Tell whether a node was started so recently that it may simply not have appeared yet.

        @param name: the node's name.
        @return: True within the grace period after starting it.
        """
        return self._clock() - self._started.get(name, -math.inf) < self._timing.grace

    def _stop_duplicates(self, names: NodeNames, graph: Graph) -> None:
        """Stop every gain stage beyond the first with the same name.

        A stage started twice would leave two nodes sharing a name, and
        whichever a snapshot listed first would get the links, so the
        wiring would change from one pass to the next.

        @param names: the mic's node names.
        @param graph: the current snapshot.
        """
        stage_names = {node.name for node in graph.nodes if names.stage_id(node.name) is not None}
        self._terminate(extra for name in stage_names for extra in graph.nodes_named(name)[1:])

    def _stop_stale(self, profile: MicProfile, names: NodeNames, graph: Graph) -> None:
        current = {settings.id for settings in profile.inputs}
        self._terminate(
            node
            for node in graph.nodes
            if (stage := names.stage_id(node.name)) is not None and stage not in current
        )

    def _terminate(self, nodes: Iterable[Node | None]) -> None:
        for pid in {node.process_id for node in nodes if node and node.process_id}:
            self._launcher.terminate(pid, STAGE_PROGRAM)

    @staticmethod
    def _ready(graph: Graph, name: str) -> bool:
        """Tell whether a node can be linked yet.

        PipeWire publishes a new node a moment before its ports. Linking in
        that gap finds nothing to link, so a node only counts once it has ports.

        @param graph: the current snapshot.
        @param name: the node's name.
        @return: True once the node exists with at least one port.
        """
        node = graph.node(name)
        return node is not None and bool(node.inputs or node.outputs)

    def _await(self, names: list[str]) -> Graph:
        graph = self._graph.snapshot()
        for _ in range(self._timing.attempts):
            if all(self._ready(graph, name) for name in names):
                break
            self._sleep(self._timing.interval)
            graph = self._graph.snapshot()
        return graph
