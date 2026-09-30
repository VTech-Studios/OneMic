import json

from onemic.infrastructure.gain_stage import PwLoopbackStages, node_properties
from onemic.infrastructure.taps import PwRecordTaps
from onemic.infrastructure.virtual_mic import PactlVirtualMic
from onemic.infrastructure.volume import WpctlVolume
from tests.fakes import FakeLauncher, FakeRunner

MODULES = (
    "12\tmodule-null-sink\tsink_name=onemic.lesson media.class=Audio/Source/Virtual\t\n"
    "13\tmodule-null-sink\tsink_name=onemic.lesson-2 media.class=Audio/Source/Virtual\t\n"
    "14\tmodule-loopback\tsink_name=onemic.lesson\t\n"
    "15\tmodule-null-sink\tsink_name=onemic.lesson channel_map=front-left,front-right\t\n"
)


def test_virtual_mic_is_a_null_sink_with_a_quoted_description() -> None:
    runner = FakeRunner()

    PactlVirtualMic(runner).create("onemic.lesson", "Guitar Lesson (OneMic)")

    assert runner.calls == [
        [
            "pactl",
            "load-module",
            "module-null-sink",
            "media.class=Audio/Source/Virtual",
            "sink_name=onemic.lesson",
            "channel_map=front-left,front-right",
            "sink_properties='device.description=\"Guitar Lesson (OneMic)\"'",
        ]
    ]


def test_removing_a_mic_unloads_only_its_null_sinks() -> None:
    runner = FakeRunner([(["pactl", "list"], MODULES)])

    PactlVirtualMic(runner).remove("onemic.lesson")

    assert runner.calls[1:] == [["pactl", "unload-module", "12"], ["pactl", "unload-module", "15"]]


def test_volume_and_mute_use_wpctl() -> None:
    runner = FakeRunner()
    volume = WpctlVolume(runner)

    volume.set_volume(42, 0.75)
    volume.set_muted(42, True)
    volume.set_muted(42, False)

    assert runner.calls == [
        ["wpctl", "set-volume", "42", "0.750"],
        ["wpctl", "set-mute", "42", "1"],
        ["wpctl", "set-mute", "42", "0"],
    ]


def test_node_properties_disable_autoconnect_and_quote_safely() -> None:
    props = json.loads(node_properties("onemic.a.in.b", 'Say "hi"'))

    assert props == {"node.name": "onemic.a.in.b", "node.description": 'Say "hi"', "node.autoconnect": False}


def test_gain_stages_run_as_detached_loopbacks() -> None:
    launcher = FakeLauncher()

    PwLoopbackStages(launcher).start("stage.in", "stage.out", "OneMic Lesson: Voice")

    [args] = launcher.spawned
    assert args[:3] == ["pw-loopback", "--channels", "2"]
    assert json.loads(args[args.index("--capture-props") + 1])["node.name"] == "stage.in"
    playback = json.loads(args[args.index("--playback-props") + 1])
    assert playback["node.name"] == "stage.out"
    assert playback["node.description"] == "OneMic Lesson: Voice (out)"


def test_taps_record_raw_float_stereo_without_autolinking() -> None:
    launcher = FakeLauncher()

    PwRecordTaps(launcher).open("onemic.lesson.tap.mix")

    [args] = launcher.streams
    assert args[0] == "pw-record"
    assert args[args.index("--format") + 1] == "f32"
    assert args[args.index("--target") + 1] == "0"
    assert json.loads(args[args.index("--properties") + 1])["node.autoconnect"] is False
    assert args[-1] == "-"
