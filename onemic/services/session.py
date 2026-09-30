from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ..domain.errors import AudioError
from ..domain.graph import Graph, Link, Node
from ..domain.naming import NodeNames
from ..domain.profile import MicProfile
from ..domain.stage import StageControls, stage_controls
from ..ports import AudioGraph, StageControl, VolumeControl
from .routing import InputState, Routing, preview, route
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
    """Sends levels and filter settings to PipeWire only when they actually change.

    Every pass re-applies them, so without the cache a control left alone
    would still cost a command per input every second. The cache is keyed
    by serial, which PipeWire never reuses, so a restarted node is always
    given its settings.
    """

    def __init__(self, volumes: VolumeControl, stages: StageControl) -> None:
        self._volumes = volumes
        self._stages = stages
        self._sent: dict[int, object] = {}

    def mic(self, node: Node | None, gain: float, muted: bool) -> None:
        """Set the mic's master volume and mute.

        @param node: the mic's node, or None if it does not exist yet.
        @param gain: the wanted volume, where 1.0 is unity.
        @param muted: the wanted mute state.
        """
        self._send(node, (gain, muted), lambda target: self._set_mic(target, gain, muted))

    def stage(self, node: Node | None, controls: StageControls) -> None:
        """Set a gain stage's low-cut, gain and gate.

        @param node: the stage's capture node, or None if it does not exist yet.
        @param controls: the values to send.
        """
        self._send(node, controls, lambda target: self._stages.set_controls(target.id, controls))

    def forget(self) -> None:
        """Drop the cache once nothing it describes exists any more."""
        self._sent.clear()

    def _set_mic(self, node: Node, gain: float, muted: bool) -> None:
        self._volumes.set_volume(node.id, gain)
        self._volumes.set_muted(node.id, muted)

    def _send(self, node: Node | None, value: object, action: Callable[[Node], None]) -> None:
        """Run a change if the value differs from what was last sent.

        A node can vanish between the snapshot and the change. That failure
        is logged and not cached, so the next pass tries again.

        @param node: the node to change.
        @param value: what it should be set to.
        @param action: sends the change.
        """
        if node is None or self._sent.get(node.serial) == value:
            return
        try:
            action(node)
        except AudioError as error:
            log.info("Level change skipped: %s", error)
            return
        self._sent[node.serial] = value


class MicSession:
    """Owns the one live mic, or the mic being set up before it goes live.

    Every change reads the graph and converges it on the wanted state, so
    any call can safely be repeated after a failure. Creating and removing
    nodes is delegated to the NodeSupervisor.
    """

    def __init__(
        self, *, graph: AudioGraph, supervisor: NodeSupervisor, volumes: VolumeControl, stages: StageControl
    ) -> None:
        self._graph = graph
        self._supervisor = supervisor
        self._levels = LevelApplier(volumes, stages)
        self._profile: MicProfile | None = None
        self._previewing: MicProfile | None = None
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

        Stages already running from previewing this mic are kept, so going
        live adds the mic without a gap in the audio. If building the mic
        fails part-way, whatever was built is removed again.

        @param profile: the mic to make live.
        @return: the status after the mic was built and linked.
        @raise AudioError: if the mic could not be built.
        """
        self._supervisor.teardown(self._graph.snapshot(), keep=NodeNames(profile.slug))
        self._profile, self._previewing = profile, None
        try:
            return self.reconcile()
        except AudioError:
            self._abandon()
            raise

    def update(self, profile: MicProfile) -> SessionStatus:
        """Apply edited settings, such as an added or removed input.

        @param profile: the edited mic.
        @return: the status after the change.
        """
        if self._is_previewing(profile):
            return self.preview(profile)
        if not self._is_live(profile):
            return self.status()
        self._profile = profile
        return self.reconcile()

    def apply_levels(self, profile: MicProfile) -> None:
        """Apply only level and filter changes, live or while previewing.

        Reads a fresh snapshot, because node ids from an older one may have
        been reused by another application's stream since.

        @param profile: the edited mic.
        """
        if self._is_live(profile):
            self._profile = profile
        elif self._is_previewing(profile):
            self._previewing = profile
        else:
            return
        self._apply_levels(profile, self._graph.snapshot())

    def set_listening(self, listening: bool) -> SessionStatus:
        """Hear the mic, or the inputs being previewed, through the default output.

        @param listening: True to listen.
        @return: the status after the change.
        @raise AudioError: if the change failed, in which case the old setting is kept.
        """
        previous, self._listening = self._listening, listening
        try:
            if self._profile is not None:
                return self.reconcile()
            if self._previewing is not None:
                return self.preview(self._previewing)
        except AudioError:
            self._listening = previous
            raise
        return self.status()

    def preview(self, profile: MicProfile) -> SessionStatus:
        """Run a mic's gain stages without the mic, so it can be set up before going live.

        Meters and Listen then show each input exactly as it will be sent.
        Stages left from previewing a different mic are removed. Does nothing
        while a mic is live.

        @param profile: the mic being set up.
        @return: the status, which stays not live.
        """
        if self._profile is not None:
            return self.status()
        graph = self._graph.snapshot()
        if self._previewing is not None and self._previewing.slug != profile.slug:
            self._supervisor.remove(graph, NodeNames(self._previewing.slug))
            self._heard.clear()
        self._previewing = profile
        graph = self._supervisor.ensure(profile, graph, with_mic=False)
        routing = preview(profile, graph, self._listening, self._remember_listening(graph))
        self._apply_links(routing)
        self._apply_levels(profile, graph)
        self._settle_listening()
        self._last_graph = graph
        return SessionStatus(
            listening=self._listening, listen_blocked=routing.listen_blocked, inputs=routing.inputs
        )

    def stop(self) -> SessionStatus:
        """Take down every OneMic mic and gain stage.

        @return: the status, no longer live.
        """
        self._supervisor.teardown(self._graph.snapshot(), keep=None)
        self._forget()
        return SessionStatus()

    def close(self, keep_live: bool) -> None:
        """Leave things as they should be when the application exits.

        A live mic the user chose to keep stays up without Listen, since
        nothing would be left to switch Listen off. Anything else, including
        stages that were only previewing, is removed.

        @param keep_live: True to leave a live mic running.
        """
        if keep_live and self._profile is not None:
            self.set_listening(False)
        elif self._profile is not None:
            self.stop()
        elif self._previewing is not None:
            self._supervisor.remove(self._graph.snapshot(), NodeNames(self._previewing.slug))

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
        routing = route(profile, graph, self._listening, self._remember_listening(graph))
        self._apply_links(routing)
        self._apply_levels(profile, graph)
        self._settle_listening()
        self._last_graph = graph
        return self._status(profile, routing)

    def status(self) -> SessionStatus:
        """Report the status from the last snapshot, without touching the graph.

        @return: the last known status of the live mic, if any.
        """
        profile = self._profile
        if profile is None:
            return SessionStatus(listening=self._listening)
        return self._status(profile, route(profile, self._last_graph, self._listening, self._heard))

    def _remember_listening(self, graph: Graph) -> set[str]:
        """Note which output listening uses, so its links can be found and removed later.

        The output is remembered even after the default output changes to
        another device, which is how the old device's links get removed.

        @param graph: the current snapshot.
        @return: every output listening has been linked to.
        """
        if self._listening and graph.default_sink:
            self._heard.add(graph.default_sink)
        return self._heard

    def _settle_listening(self) -> None:
        if not self._listening:
            self._heard.clear()

    def _is_live(self, profile: MicProfile) -> bool:
        return self._profile is not None and self._profile.slug == profile.slug

    def _is_previewing(self, profile: MicProfile) -> bool:
        return self._previewing is not None and self._previewing.slug == profile.slug

    def _abandon(self) -> None:
        """Remove a half-built mic after a failure, keeping the original failure as the one reported."""
        with contextlib.suppress(AudioError):
            self._supervisor.teardown(self._graph.snapshot(), keep=None)
        self._forget()

    def _forget(self) -> None:
        self._profile = None
        self._previewing = None
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
        self._levels.mic(graph.node(names.mic), profile.gain, profile.muted)
        for settings in profile.inputs:
            controls = stage_controls(settings, profile.is_silenced(settings))
            self._levels.stage(graph.node(names.stage_input(settings.id)), controls)

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
