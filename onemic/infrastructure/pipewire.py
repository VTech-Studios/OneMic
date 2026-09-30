from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..domain.errors import AudioError
from ..domain.graph import Graph, Link, Node, Port
from ..ports import CommandRunner

JsonObject = Mapping[str, Any]

_NODE = "PipeWire:Interface:Node"
_PORT = "PipeWire:Interface:Port"
_LINK = "PipeWire:Interface:Link"
_CLIENT = "PipeWire:Interface:Client"
_METADATA = "PipeWire:Interface:Metadata"


def _props(item: JsonObject) -> JsonObject:
    info: JsonObject = item.get("info") or {}
    props: JsonObject = info.get("props") or {}
    return props


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except ValueError:
        return None


def _of_type(objects: Iterable[JsonObject], kind: str) -> list[JsonObject]:
    return [item for item in objects if item.get("type") == kind]


def _is_audio(props: JsonObject) -> bool:
    return "audio" in str(props.get("format.dsp", ""))


def _port(props: JsonObject, object_id: int) -> Port:
    channel = props.get("audio.channel")
    return Port(object_id, str(props.get("port.name", "")), str(channel) if channel else None)


def _ports_by_node(objects: Sequence[JsonObject]) -> dict[tuple[int, str], list[tuple[int, JsonObject]]]:
    grouped: dict[tuple[int, str], list[tuple[int, JsonObject]]] = defaultdict(list)
    for item in _of_type(objects, _PORT):
        props = _props(item)
        node_id = _as_int(props.get("node.id"))
        if node_id is not None and _is_audio(props):
            grouped[(node_id, str(props.get("port.direction")))].append((item["id"], props))
    return grouped


def _ordered(entries: list[tuple[int, JsonObject]]) -> tuple[Port, ...]:
    ranked = sorted(entries, key=lambda entry: _as_int(entry[1].get("port.id")) or 0)
    return tuple(_port(props, object_id) for object_id, props in ranked)


def _outputs(entries: list[tuple[int, JsonObject]]) -> tuple[Port, ...]:
    """Pick the output ports that carry a node's own signal.

    A sink's only outputs are its monitor ports, which carry what it plays.
    Other nodes can have monitor ports beside their real outputs, and those
    would double the signal, so they are used only when nothing else exists.

    @param entries: every audio output port of one node, with its properties.
    @return: the ports to route from, in channel order.
    """
    own = [entry for entry in entries if not entry[1].get("port.monitor")]
    return _ordered(own or entries)


def _client_processes(objects: Sequence[JsonObject]) -> dict[int, int]:
    processes: dict[int, int] = {}
    for item in _of_type(objects, _CLIENT):
        pid = _as_int(_props(item).get("application.process.id"))
        if pid is not None:
            processes[item["id"]] = pid
    return processes


def _nodes(objects: Sequence[JsonObject]) -> tuple[Node, ...]:
    ports = _ports_by_node(objects)
    processes = _client_processes(objects)
    nodes = []
    for item in _of_type(objects, _NODE):
        props = _props(item)
        node_id = item["id"]
        name = str(props.get("node.name", ""))
        client = _as_int(props.get("client.id"))
        nodes.append(
            Node(
                id=node_id,
                name=name,
                description=str(props.get("node.description") or props.get("node.nick") or name),
                media_class=str(props.get("media.class", "")),
                inputs=_ordered(ports.get((node_id, "in"), [])),
                outputs=_outputs(ports.get((node_id, "out"), [])),
                process_id=processes.get(client) if client is not None else None,
                serial=_as_int(props.get("object.serial")) or node_id,
            )
        )
    return tuple(nodes)


def _links(objects: Sequence[JsonObject]) -> frozenset[Link]:
    links = set()
    for item in _of_type(objects, _LINK):
        info: JsonObject = item.get("info") or {}
        output, into = _as_int(info.get("output-port-id")), _as_int(info.get("input-port-id"))
        if output is not None and into is not None:
            links.add(Link(output, into))
    return frozenset(links)


def _default_sink(objects: Sequence[JsonObject]) -> str | None:
    for item in _of_type(objects, _METADATA):
        if _props(item).get("metadata.name") != "default":
            continue
        for entry in item.get("metadata") or []:
            if entry.get("key") == "default.audio.sink":
                value = entry.get("value") or {}
                return str(value["name"]) if isinstance(value, Mapping) and "name" in value else None
    return None


def parse_dump(objects: Sequence[JsonObject]) -> Graph:
    """Build a graph snapshot from pw-dump's JSON.

    @param objects: the decoded array pw-dump prints.
    @return: nodes with their audio ports, links, and the default output's name.
    """
    return Graph(nodes=_nodes(objects), links=_links(objects), default_sink=_default_sink(objects))


class PipeWireGraph:
    """Reads and rewires the graph through pw-dump and pw-link.

    Both tools ship with PipeWire itself, so nothing beyond a normal
    PipeWire desktop is needed.
    """

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def snapshot(self) -> Graph:
        """Read the whole audio graph at once.

        @return: every audio node, port and link, plus the default output.
        @raise AudioError: if pw-dump fails or prints something unreadable.
        """
        output = self._runner.run(["pw-dump", "--no-colors"])
        try:
            objects = json.loads(output)
        except json.JSONDecodeError as error:
            raise AudioError("pw-dump printed something that is not JSON") from error
        return parse_dump(objects)

    def link(self, link: Link) -> None:
        """Connect an output port to an input port.

        @param link: the port ids to join.
        @raise AudioError: if PipeWire refuses the link.
        """
        self._runner.run(["pw-link", str(link.output_port), str(link.input_port)])

    def unlink(self, link: Link) -> None:
        """Disconnect an output port from an input port.

        @param link: the port ids to separate.
        @raise AudioError: if PipeWire refuses to remove the link.
        """
        self._runner.run(["pw-link", "--disconnect", str(link.output_port), str(link.input_port)])
