from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from ..domain.errors import AudioError
from ..domain.graph import Graph, Link, Node
from ..domain.naming import NodeNames, is_onemic_node, is_tap, mic_slug
from ..domain.profile import MicProfile
from ..ports import AudioGraph, GainStageDriver, ProcessLauncher, VirtualMicDriver, VolumeControl
from .routing import InputState, Routing, route

STAGE_PROGRAM = "pw-loopback"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionStatus:
    """What the interface needs to show about the live mic."""

    live_slug: str | None = None
    listening: bool = False
    listen_blocked: bool = False
    inputs: Mapping[str, InputState] = field(default_factory=dict)

    @property
    def live(self) -> bool:
        return self.live_slug is not None


@dataclass(frozen=True)
class Timing:
    """How long to wait for PipeWire to publish nodes that were just started.

    Nodes appear a moment after their process starts. Waiting briefly lets
    the first pass link everything, instead of leaving the mic silent until
    the next pass a second later.
    """

    attempts: int = 20
    interval: float = 0.05


class LevelApplier:
    """Sends volume and mute changes to PipeWire only when they actually change.

    Every routing pass re-applies levels, so without the cache a slider left
    alone would still cost two wpctl calls per input every second.
    """

    def __init__(self, volumes: VolumeControl) -> None:
        self._volumes = volumes
        self._applied: dict[int, tuple[float, bool]] = {}

    def apply(self, node: Node | None, gain: float, muted: bool) -> None:
        """Set a node's level if it differs from what was last sent.

        @param node: the node to change, or None if it does not exist yet.
        @param gain: the wanted volume, where 1.0 is unity.
        @param muted: the wanted mute state.
        """
        if node is None or self._applied.get(node.serial) == (gain, muted):
            return
        self._volumes.set_volume(node.id, gain)
        self._volumes.set_muted(node.id, muted)
        self._applied[node.serial] = (gain, muted)

    def forget(self) -> None:
        """Drop the cache once nothing it describes exists any more."""
        self._applied.clear()


class MicSession:
    """Owns the one live mic: builds it, keeps it wired, and takes it down.

    Every method reads the graph and converges it on the wanted state, so
    any of them can safely be called again after a failure.
    """

    def __init__(
        self,
        *,
        graph: AudioGraph,
        mics: VirtualMicDriver,
        stages: GainStageDriver,
        volumes: VolumeControl,
        launcher: ProcessLauncher,
        timing: Timing | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._graph = graph
        self._mics = mics
        self._stages = stages
        self._levels = LevelApplier(volumes)
        self._launcher = launcher
        self._timing = timing or Timing()
        self._sleep = sleep
        self._profile: MicProfile | None = None
        self._listening = False
        self._last_graph = Graph()

    def adopt(self, profiles: Sequence[MicProfile]) -> SessionStatus:
        """Take over a mic left live by an earlier run, if there is one.

        @param profiles: every saved mic.
        @return: the status, live if one of the mics already exists in the graph.
        """
        graph = self._graph.snapshot()
        self._profile = next((item for item in profiles if graph.node(NodeNames(item.slug).mic)), None)
        return self.reconcile() if self._profile else SessionStatus()

    def go_live(self, profile: MicProfile) -> SessionStatus:
        """Make a mic live, taking down any other OneMic mic first.

        Only one mic is live at a time, so a call application never has two
        OneMic devices with half the inputs each to choose between.

        @param profile: the mic to make live.
        @return: the status after the mic was built and linked.
        """
        self._teardown(self._graph.snapshot(), keep=NodeNames(profile.slug))
        self._profile = profile
        return self.reconcile()

    def update(self, profile: MicProfile) -> SessionStatus:
        """Apply edited settings, such as an added or removed input.

        @param profile: the edited mic.
        @return: the status after the change, or not live if a different mic was edited.
        """
        if self._profile is None or self._profile.slug != profile.slug:
            return self.status()
        self._profile = profile
        return self.reconcile()

    def apply_levels(self, profile: MicProfile) -> None:
        """Apply only volume and mute changes, without reading the graph.

        Dragging a slider sends many changes a second. Reusing the last
        snapshot keeps each one to a single wpctl call.

        @param profile: the edited mic.
        """
        if self._profile is None or self._profile.slug != profile.slug:
            return
        self._profile = profile
        self._apply_levels(profile, self._last_graph)

    def set_listening(self, listening: bool) -> SessionStatus:
        """Play the mic through the default output, or stop doing so.

        @param listening: True to hear what the mic is sending.
        @return: the status after the change.
        """
        self._listening = listening
        return self.reconcile() if self._profile else self.status()

    def stop(self) -> SessionStatus:
        """Take down every OneMic mic and gain stage.

        @return: the status, no longer live.
        """
        self._teardown(self._graph.snapshot(), keep=None)
        self._profile = None
        self._listening = False
        self._levels.forget()
        return SessionStatus()

    def reconcile(self) -> SessionStatus:
        """Converge the graph on the live mic's settings.

        Missing nodes are started, stale gain stages stopped, links added and
        removed, and levels applied. Called on a timer while live, this is
        what relinks an application that was opened after the mic went live.

        @return: the status after this pass.
        """
        profile = self._profile
        if profile is None:
            return SessionStatus()
        graph = self._ensure_nodes(profile, self._graph.snapshot())
        self._stop_stale_stages(profile, graph)
        routing = route(profile, graph, self._listening)
        self._apply_links(routing)
        self._apply_levels(profile, graph)
        self._last_graph = graph
        return self._status(profile, routing)

    def status(self) -> SessionStatus:
        """Report the status without touching the graph.

        @return: the last known status of the live mic, if any.
        """
        profile = self._profile
        if profile is None:
            return SessionStatus()
        return self._status(profile, route(profile, self._last_graph, self._listening))

    def _status(self, profile: MicProfile, routing: Routing) -> SessionStatus:
        return SessionStatus(
            live_slug=profile.slug,
            listening=self._listening,
            listen_blocked=routing.listen_blocked,
            inputs=routing.inputs,
        )

    def _ensure_nodes(self, profile: MicProfile, graph: Graph) -> Graph:
        names = NodeNames(profile.slug)
        wanted = [names.mic]
        if graph.node(names.mic) is None:
            self._mics.create(names.mic, f"{profile.name} (OneMic)")
        for settings in profile.inputs:
            pair = [names.stage_input(settings.id), names.stage_output(settings.id)]
            wanted += pair
            if any(graph.node(name) is None for name in pair):
                self._restart_stage(graph, pair, f"OneMic {profile.name}: {settings.label}")
        missing = [name for name in wanted if not self._ready(graph, name)]
        return self._await(missing) if missing else graph

    def _restart_stage(self, graph: Graph, pair: list[str], description: str) -> None:
        self._terminate(graph.node(name) for name in pair)
        self._stages.start(pair[0], pair[1], description)

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

    def _await(self, names: Iterable[str]) -> Graph:
        wanted = list(names)
        graph = self._graph.snapshot()
        for _ in range(self._timing.attempts):
            if all(self._ready(graph, name) for name in wanted):
                break
            self._sleep(self._timing.interval)
            graph = self._graph.snapshot()
        return graph

    def _stop_stale_stages(self, profile: MicProfile, graph: Graph) -> None:
        names = NodeNames(profile.slug)
        current = {settings.id for settings in profile.inputs}
        self._terminate(
            node
            for node in graph.nodes
            if (stage := names.stage_id(node.name)) is not None and stage not in current
        )

    def _terminate(self, nodes: Iterable[Node | None]) -> None:
        for pid in {node.process_id for node in nodes if node and node.process_id}:
            self._launcher.terminate(pid, STAGE_PROGRAM)

    def _teardown(self, graph: Graph, keep: NodeNames | None) -> None:
        doomed = [
            node
            for node in graph.nodes
            if is_onemic_node(node.name) and not is_tap(node.name) and not (keep and keep.owns(node.name))
        ]
        for node in doomed:
            if mic_slug(node.name) is not None:
                self._mics.remove(node.name)
        self._terminate(node for node in doomed if mic_slug(node.name) is None)

    def _apply_links(self, routing: Routing) -> None:
        for link in routing.to_remove:
            self._try(self._graph.unlink, link)
        for link in routing.to_create:
            self._try(self._graph.link, link)

    def _apply_levels(self, profile: MicProfile, graph: Graph) -> None:
        names = NodeNames(profile.slug)
        self._levels.apply(graph.node(names.mic), profile.gain, profile.muted)
        for settings in profile.inputs:
            self._levels.apply(graph.node(names.stage_output(settings.id)), settings.gain, settings.muted)

    @staticmethod
    def _try(action: Callable[[Link], None], link: Link) -> None:
        """Attempt one link change without abandoning the rest of the pass.

        A port can vanish between the snapshot and the change, for example
        when an application quits. The next pass sees the new graph and
        corrects itself, so one failure is logged rather than raised.

        @param action: link or unlink.
        @param link: the ports involved.
        """
        try:
            action(link)
        except AudioError as error:
            log.info("Link change skipped: %s", error)
