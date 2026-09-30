from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum

from ..domain.graph import Graph, Link, Node, pair_channels
from ..domain.naming import NodeNames
from ..domain.profile import InputSettings, MicProfile


class InputState(Enum):
    OFF = "off"
    STARTING = "starting"
    WAITING = "waiting"
    LIVE = "live"


@dataclass(frozen=True)
class Routing:
    """How one live mic should be wired, worked out from a single graph snapshot.

    The graph is compared against this on every pass. Anything missing is
    linked and anything stale is removed, so the same code both builds a
    mic and repairs it after a device or application comes back.
    """

    desired: frozenset[Link]
    managed: frozenset[Link]
    inputs: Mapping[str, InputState]
    listen_blocked: bool

    @property
    def to_create(self) -> frozenset[Link]:
        """Desired links that do not exist yet.

        Every desired link touches a node the mic manages, so one that
        already exists is always among the managed links.

        @return: the links to make.
        """
        return self.desired - self.managed

    @property
    def to_remove(self) -> frozenset[Link]:
        """Managed links that are no longer wanted.

        @return: the links to break.
        """
        return self.managed - self.desired


def input_state(settings: InputSettings, graph: Graph, names: NodeNames) -> InputState:
    """Describe how far one input has got towards being heard.

    @param settings: the input.
    @param graph: the current snapshot.
    @param names: the node names of the mic the input belongs to.
    @return: STARTING until its gain stage exists, WAITING while its source
        is absent or has no outputs yet, then LIVE.
    """
    if (
        graph.node(names.stage_input(settings.id)) is None
        or graph.node(names.stage_output(settings.id)) is None
    ):
        return InputState.STARTING
    source = graph.node(settings.source)
    if source is None or not source.outputs:
        return InputState.WAITING
    return InputState.LIVE


def _join(source: Node | None, destination: Node | None) -> frozenset[Link]:
    if source is None or destination is None:
        return frozenset()
    return pair_channels(source.outputs, destination.inputs)


def _input_links(
    settings: InputSettings, graph: Graph, names: NodeNames, mic: Node | None
) -> frozenset[Link]:
    stage_in = graph.node(names.stage_input(settings.id))
    stage_out = graph.node(names.stage_output(settings.id))
    return (
        _join(graph.node(settings.source), stage_in)
        | _join(stage_out, mic)
        | _join(stage_out, graph.node(names.tap(settings.id)))
    )


def is_listen_blocked(profile: MicProfile, graph: Graph) -> bool:
    """Tell whether listening would feed the mic back into itself.

    Listening plays the mic through the default output. If that output is
    also one of the mic's inputs, the mic would hear itself and howl.

    @param profile: the live mic.
    @param graph: the current snapshot.
    @return: True if listening must stay off.
    """
    return any(settings.source == graph.default_sink for settings in profile.inputs)


def _listen_links(graph: Graph, mic: Node | None) -> frozenset[Link]:
    sink = graph.node(graph.default_sink) if graph.default_sink else None
    return _join(mic, sink)


def managed_links(graph: Graph, names: NodeNames, heard: Collection[str]) -> frozenset[Link]:
    """Collect the existing links this mic is responsible for.

    That is everything into the mic's own nodes, everything out of its gain
    stages, and the mic's links to the outputs OneMic itself played it
    through. A call application recording the mic, or a link the user made
    by hand from the mic to any other output, is left alone.

    @param graph: the current snapshot.
    @param names: the node names of the mic.
    @param heard: names of the outputs OneMic has linked the mic to for listening.
    @return: the links a routing pass may keep or remove.
    """
    owned = [node for node in graph.nodes if names.owns(node.name)]
    inputs = {port.id for node in owned for port in node.inputs}
    outputs = {port.id for node in owned if node.name != names.mic for port in node.outputs}
    mic = graph.node(names.mic)
    mic_outputs = {port.id for port in mic.outputs} if mic else set()
    speakers = {port.id for node in graph.nodes if node.name in heard for port in node.inputs}
    return frozenset(
        link
        for link in graph.links
        if link.input_port in inputs
        or link.output_port in outputs
        or (link.output_port in mic_outputs and link.input_port in speakers)
    )


def route(profile: MicProfile, graph: Graph, listening: bool, heard: Collection[str] = ()) -> Routing:
    """Work out the complete wiring for a live mic.

    @param profile: the live mic.
    @param graph: the current snapshot.
    @param listening: True to also play the mic through the default output.
    @param heard: names of the outputs OneMic has linked the mic to for listening,
        so those links can be removed when listening stops or the default output changes.
    @return: the desired and existing links, and each input's state.
    """
    names = NodeNames(profile.slug)
    mic = graph.node(names.mic)
    blocked = is_listen_blocked(profile, graph)
    desired = _join(mic, graph.node(names.mix_tap))
    for settings in profile.inputs:
        desired |= _input_links(settings, graph, names, mic)
    if listening and not blocked:
        desired |= _listen_links(graph, mic)
    return Routing(
        desired=desired,
        managed=managed_links(graph, names, heard),
        inputs={settings.id: input_state(settings, graph, names) for settings in profile.inputs},
        listen_blocked=blocked,
    )


def preview(profile: MicProfile, graph: Graph, listening: bool, heard: Collection[str] = ()) -> Routing:
    """Work out the wiring for setting a mic up before it goes live.

    Each input runs through its gain stage exactly as it will when live, so
    its meter and Listen show the input with its volume, mute, solo and
    filters applied. There is no mic yet, so Listen plays the stages
    straight to the default output instead.

    @param profile: the mic being set up.
    @param graph: the current snapshot.
    @param listening: True to hear the processed inputs through the default output.
    @param heard: names of the outputs OneMic has linked for listening.
    @return: the preview links, with every input's state OFF.
    """
    names = NodeNames(profile.slug)
    blocked = is_listen_blocked(profile, graph)
    sink = graph.node(graph.default_sink) if listening and not blocked and graph.default_sink else None
    desired: frozenset[Link] = frozenset()
    for settings in profile.inputs:
        stage_out = graph.node(names.stage_output(settings.id))
        desired |= _join(graph.node(settings.source), graph.node(names.stage_input(settings.id)))
        desired |= _join(stage_out, graph.node(names.tap(settings.id))) | _join(stage_out, sink)
    return Routing(
        desired=desired,
        managed=managed_links(graph, names, heard),
        inputs={settings.id: InputState.OFF for settings in profile.inputs},
        listen_blocked=blocked,
    )
