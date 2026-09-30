from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import media
from .graph import Graph, Node
from .naming import is_onemic_node


class SourceKind(Enum):
    MICROPHONE = "Microphones and inputs"
    APPLICATION = "Applications"
    PLAYBACK = "Speakers and outputs (what they play)"


@dataclass(frozen=True)
class AudioSource:
    name: str
    description: str
    kind: SourceKind


_KIND_BY_CLASS = {
    media.SOURCE: SourceKind.MICROPHONE,
    media.VIRTUAL_SOURCE: SourceKind.MICROPHONE,
    media.DUPLEX: SourceKind.MICROPHONE,
    media.SINK: SourceKind.PLAYBACK,
    media.APPLICATION_OUTPUT: SourceKind.APPLICATION,
    media.APPLICATION_DUPLEX: SourceKind.APPLICATION,
}


def classify(node: Node) -> SourceKind | None:
    """Decide whether a node can feed a mic, and how to describe it.

    Internal nodes (splitters and the like) are PipeWire plumbing that would
    only confuse the list, and OneMic's own nodes would make a feedback loop.

    @param node: any node from a graph snapshot.
    @return: the kind of source, or None if it should not be offered.
    """
    if not node.outputs or is_onemic_node(node.name):
        return None
    return _KIND_BY_CLASS.get(node.media_class)


def available_sources(graph: Graph) -> list[AudioSource]:
    """List every signal the user could add to a mic, grouped and sorted for display.

    @param graph: a snapshot of the audio graph.
    @return: one entry per usable node, ordered by kind and then description.
    """
    sources = [
        AudioSource(node.name, node.description, kind)
        for node in graph.nodes
        if (kind := classify(node)) is not None
    ]
    order = list(SourceKind)
    return sorted(sources, key=lambda source: (order.index(source.kind), source.description.lower()))
