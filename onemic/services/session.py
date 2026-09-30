from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ..domain.errors import AudioError
from ..domain.graph import Graph, Link, Node
from ..domain.naming import NodeNames
from ..domain.profile import MicProfile
from ..ports import AudioGraph, VolumeControl
from .routing import InputState, Routing, route
from .supervisor import NodeSupervisor

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


class LevelApplier:
    """Sends volume and mute changes to PipeWire only when they actually change.

    Every routing pass re-applies levels, so without the cache a slider left
    alone would still cost two wpctl calls per input every second. The cache
    is keyed by serial, which PipeWire never reuses, so a restarted node is
    always given its levels.
    """

    def __init__(self, volumes: VolumeControl) -> None:
        self._volumes = volumes
        self._applied: dict[int, tuple[float, bool]] = {}

    def apply(self, node: Node | None, gain: float, muted: bool) -> None:
        """Set a node's level if it differs from what was last sent.

        A node can vanish between the snapshot and the change. That failure
        is logged and not cached, so the next pass tries again.

        @param node: the node to change, or None if it does not exist yet.
        @param gain: the wanted volume, where 1.0 is unity.
        @param muted: the wanted mute state.
        """
        if node is None or self._applied.get(node.serial) == (gain, muted):
            return
        try:
            self._volumes.set_volume(node.id, gain)
            self._volumes.set_muted(node.id, muted)
        except AudioError as error:
            log.info("Level change skipped: %s", error)
            return
        self._applied[node.serial] = (gain, muted)

    def forget(self) -> None:
        """Drop the cache once nothing it describes exists any more."""
        self._applied.clear()


class MicSession:
    """Owns the one live mic: which it is, how it is wired, and how loud each part is.

    Every change reads the graph and converges it on the wanted state, so
    any call can safely be repeated after a failure. Creating and removing
    nodes is delegated to the NodeSupervisor.
    """

    def __init__(self, *, graph: AudioGraph, supervisor: NodeSupervisor, volumes: VolumeControl) -> None:
        self._graph = graph
        self._supervisor = supervisor
        self._levels = LevelApplier(volumes)
        self._profile: MicProfile | None = None
        self._listening = False
        self._heard: set[str] = set()
        self._last_graph = Graph()

    def adopt(self, profiles: Sequence[MicProfile]) -> SessionStatus:
        """Take over a mic left live by an earlier run, if there is one.

        If an earlier crash left more than one mic live, all but the first are
        removed, so only one OneMic device is ever offered to call apps.

        @param profiles: every saved mic.
        @return: the status, live if one of the mics already exists in the graph.
        """
        graph = self._graph.snapshot()
        found = next((item for item in profiles if graph.node(NodeNames(item.slug).mic)), None)
        if found is None:
            return SessionStatus()
        self._supervisor.teardown(graph, keep=NodeNames(found.slug))
        self._profile = found
        return self.reconcile()

    def go_live(self, profile: MicProfile) -> SessionStatus:
        """Make a mic live, taking down any other OneMic mic first.

        If building the mic fails part-way, whatever was built is removed
        again, so a failure never leaves a half-made device behind.

        @param profile: the mic to make live.
        @return: the status after the mic was built and linked.
        @raise AudioError: if the mic could not be built.
        """
        self._supervisor.teardown(self._graph.snapshot(), keep=NodeNames(profile.slug))
        self._profile = profile
        try:
            return self.reconcile()
        except AudioError:
            self._abandon()
            raise

    def update(self, profile: MicProfile) -> SessionStatus:
        """Apply edited settings, such as an added or removed input.

        @param profile: the edited mic.
        @return: the status after the change, or not live if a different mic was edited.
        """
        if not self._is_live(profile):
            return self.status()
        self._profile = profile
        return self.reconcile()

    def apply_levels(self, profile: MicProfile) -> None:
        """Apply only volume and mute changes.

        Reads a fresh snapshot, because node ids from an older one may have
        been reused by another application's stream since.

        @param profile: the edited mic.
        """
        if not self._is_live(profile):
            return
        self._profile = profile
        self._apply_levels(profile, self._graph.snapshot())

    def set_listening(self, listening: bool) -> SessionStatus:
        """Play the mic through the default output, or stop doing so.

        @param listening: True to hear what the mic is sending.
        @return: the status after the change.
        @raise AudioError: if the change failed, in which case the old setting is kept.
        """
        previous, self._listening = self._listening, listening
        if self._profile is None:
            return self.status()
        try:
            return self.reconcile()
        except AudioError:
            self._listening = previous
            raise

    def stop(self) -> SessionStatus:
        """Take down every OneMic mic and gain stage.

        @return: the status, no longer live.
        """
        self._supervisor.teardown(self._graph.snapshot(), keep=None)
        self._forget()
        return SessionStatus()

    def reconcile(self) -> SessionStatus:
        """Converge the graph on the live mic's settings.

        Missing nodes are started, stale ones stopped, links added and removed,
        and levels applied. Called on a timer while live, this is what relinks
        an application that was opened after the mic went live.

        @return: the status after this pass.
        """
        profile = self._profile
        if profile is None:
            return SessionStatus()
        graph = self._supervisor.ensure(profile, self._graph.snapshot())
        routing = self._route(profile, graph)
        self._apply_links(routing)
        self._apply_levels(profile, graph)
        if not self._listening:
            self._heard.clear()
        self._last_graph = graph
        return self._status(profile, routing)

    def status(self) -> SessionStatus:
        """Report the status from the last snapshot, without touching the graph.

        @return: the last known status of the live mic, if any.
        """
        profile = self._profile
        if profile is None:
            return SessionStatus()
        return self._status(profile, route(profile, self._last_graph, self._listening, self._heard))

    def _route(self, profile: MicProfile, graph: Graph) -> Routing:
        """Plan the wiring, remembering which output listening uses.

        The output is remembered so its links can be found and removed later,
        even after the default output has changed to another device.

        @param profile: the live mic.
        @param graph: the current snapshot.
        @return: the routing for this pass.
        """
        if self._listening and graph.default_sink:
            self._heard.add(graph.default_sink)
        return route(profile, graph, self._listening, self._heard)

    def _is_live(self, profile: MicProfile) -> bool:
        return self._profile is not None and self._profile.slug == profile.slug

    def _abandon(self) -> None:
        """Remove a half-built mic after a failure, keeping the original failure as the one reported."""
        with contextlib.suppress(AudioError):
            self._supervisor.teardown(self._graph.snapshot(), keep=None)
        self._forget()

    def _forget(self) -> None:
        self._profile = None
        self._listening = False
        self._heard.clear()
        self._levels.forget()

    def _status(self, profile: MicProfile, routing: Routing) -> SessionStatus:
        return SessionStatus(
            live_slug=profile.slug,
            listening=self._listening,
            listen_blocked=routing.listen_blocked,
            inputs=routing.inputs,
        )

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
