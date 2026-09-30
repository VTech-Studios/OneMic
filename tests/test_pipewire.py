import json
from typing import Any

import pytest

from onemic.domain.errors import AudioError
from onemic.domain.graph import Link
from onemic.infrastructure.pipewire import PipeWireGraph, parse_dump
from tests.fakes import FakeRunner


def port(object_id: int, node: int, name: str, direction: str, index: int, **extra: Any) -> dict[str, Any]:
    props = {
        "node.id": node,
        "port.name": name,
        "port.direction": direction,
        "port.id": index,
        "format.dsp": "32 bit float mono audio",
        **extra,
    }
    return {"id": object_id, "type": "PipeWire:Interface:Port", "info": {"props": props}}


def node(object_id: int, name: str, media_class: str, **extra: Any) -> dict[str, Any]:
    props = {"node.name": name, "node.description": name.title(), "media.class": media_class, **extra}
    return {"id": object_id, "type": "PipeWire:Interface:Node", "info": {"props": props}}


DUMP: list[dict[str, Any]] = [
    {"id": 60, "type": "PipeWire:Interface:Client", "info": {"props": {"application.process.id": 4321}}},
    node(1, "reaper", "Stream/Output/Audio", **{"client.id": 60, "object.serial": 900}),
    port(12, 1, "out2", "out", 1),
    port(11, 1, "out1", "out", 0),
    port(13, 1, "midi_out", "out", 2, **{"format.dsp": "8 bit raw midi"}),
    node(2, "speakers", "Audio/Sink"),
    port(21, 2, "playback_FL", "in", 0, **{"audio.channel": "FL"}),
    port(22, 2, "monitor_FL", "out", 0, **{"port.monitor": True}),
    node(3, "loop", "Stream/Input/Audio"),
    port(31, 3, "capture_FL", "out", 0),
    port(32, 3, "monitor_FL", "out", 1, **{"port.monitor": True}),
    {"id": 70, "type": "PipeWire:Interface:Link", "info": {"output-port-id": 11, "input-port-id": 21}},
    {
        "id": 80,
        "type": "PipeWire:Interface:Metadata",
        "props": {"metadata.name": "default"},
        "metadata": [{"subject": 0, "key": "default.audio.sink", "value": {"name": "speakers"}}],
    },
]


def test_nodes_keep_audio_ports_in_channel_order() -> None:
    graph = parse_dump(DUMP)
    reaper = graph.node("reaper")

    assert reaper is not None
    assert [p.name for p in reaper.outputs] == ["out1", "out2"]
    assert reaper.description == "Reaper"
    assert reaper.process_id == 4321
    assert reaper.serial == 900


def test_a_sink_is_routed_from_its_monitor_ports() -> None:
    speakers = parse_dump(DUMP).node("speakers")

    assert speakers is not None
    assert [p.name for p in speakers.outputs] == ["monitor_FL"]
    assert [p.channel for p in speakers.inputs] == ["FL"]


def test_monitor_ports_are_ignored_when_a_node_has_real_outputs() -> None:
    loop = parse_dump(DUMP).node("loop")

    assert loop is not None
    assert [p.name for p in loop.outputs] == ["capture_FL"]


def test_links_and_default_sink_are_read() -> None:
    graph = parse_dump(DUMP)

    assert graph.links == {Link(11, 21)}
    assert graph.default_sink == "speakers"


def test_missing_metadata_means_no_default_sink() -> None:
    assert parse_dump([]).default_sink is None


def test_snapshot_runs_pw_dump() -> None:
    runner = FakeRunner([(["pw-dump"], json.dumps(DUMP))])

    graph = PipeWireGraph(runner).snapshot()

    assert runner.calls == [["pw-dump", "--no-colors"]]
    assert graph.node("reaper") is not None


def test_unreadable_output_is_an_audio_error() -> None:
    with pytest.raises(AudioError):
        PipeWireGraph(FakeRunner([(["pw-dump"], "not json")])).snapshot()


def test_links_are_made_and_removed_by_port_id() -> None:
    runner = FakeRunner()
    graph = PipeWireGraph(runner)

    graph.link(Link(11, 21))
    graph.unlink(Link(11, 21))

    assert runner.calls == [["pw-link", "11", "21"], ["pw-link", "--disconnect", "11", "21"]]
