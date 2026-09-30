from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    id: int
    name: str
    channel: str | None = None


@dataclass(frozen=True)
class Node:
    """One PipeWire node, reduced to what routing and control need.

    Only audio ports are kept, so a node with MIDI or video ports never looks
    like something that could feed a microphone. PipeWire reuses ids once a
    node is removed, but never reuses serials, so the serial is what tells a
    restarted node apart from the one it replaced.
    """

    id: int
    name: str
    description: str
    media_class: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    process_id: int | None = None
    serial: int = 0


@dataclass(frozen=True)
class Link:
    output_port: int
    input_port: int


@dataclass(frozen=True)
class Graph:
    """A snapshot of the audio graph at one moment.

    Everything that decides what to link reads a snapshot rather than asking
    PipeWire piecemeal, so a decision never mixes two different moments.
    """

    nodes: tuple[Node, ...] = ()
    links: frozenset[Link] = frozenset()
    default_sink: str | None = None

    def node(self, name: str) -> Node | None:
        """Find a node by its stable name.

        Names survive restarts where ids do not, which is why saved settings
        refer to sources by name.

        @param name: the node.name property.
        @return: the first node with that name, or None if absent.
        """
        return next((node for node in self.nodes if node.name == name), None)

    def nodes_named(self, name: str) -> tuple[Node, ...]:
        """Find every node with a name, oldest first.

        Names are meant to be unique, but a helper started twice leaves two
        nodes with one name, and those duplicates have to be found to be removed.

        @param name: the node.name property.
        @return: the matching nodes, ordered by serial.
        """
        return tuple(sorted((node for node in self.nodes if node.name == name), key=lambda node: node.serial))

    def links_touching(self, nodes: Iterable[Node]) -> frozenset[Link]:
        """Collect every link into or out of the given nodes.

        @param nodes: the nodes whose connections matter.
        @return: links with either end on one of those nodes' ports.
        """
        ports = {port.id for node in nodes for port in (*node.inputs, *node.outputs)}
        return frozenset(link for link in self.links if {link.output_port, link.input_port} & ports)


def pair_channels(outputs: Sequence[Port], inputs: Sequence[Port]) -> frozenset[Link]:
    """Decide which output feeds which input when joining two nodes.

    A mono signal is sent to every input, or the far end of a call hears it
    in one ear only. Otherwise channels pair up in order, and any extra
    outputs are left alone, because a DAW's first pair is its main mix.

    @param outputs: the source node's output ports, in channel order.
    @param inputs: the destination node's input ports, in channel order.
    @return: the links that join them.
    """
    if len(outputs) == 1:
        return frozenset(Link(outputs[0].id, port.id) for port in inputs)
    return frozenset(Link(out.id, into.id) for out, into in zip(outputs, inputs, strict=False))
