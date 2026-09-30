import json
from pathlib import Path

from onemic.domain.stage import StageControls
from onemic.infrastructure.gain_stage import (
    FilterChainStages,
    PwCliStageControl,
    control_values,
    node_properties,
    stage_config,
)
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


CONTROLS = StageControls(low_cut_hz=100.0, multiplier=0.5, gate_on=True, gate_threshold=0.01)
GATE = "http://lsp-plug.in/plugins/lv2/gate_mono"


def test_gain_stages_run_as_detached_filter_chains(tmp_path: Path) -> None:
    launcher = FakeLauncher()

    FilterChainStages(launcher, tmp_path / "stages", GATE).start("stage.in", "stage.out", "Voice", CONTROLS)

    config = tmp_path / "stages" / "stage.in.conf"
    assert launcher.spawned == [["pipewire", "-c", str(config)]]
    text = config.read_text()
    assert '"node.name": "stage.in"' in text
    assert '"node.name": "stage.out"' in text
    assert '"Freq" = 100.000000' in text
    assert '"Mult" = 0.500000' in text
    assert '"enabled" = 1 "gt" = 0.010000' in text
    assert 'input = "gate:in"' in text


def test_the_chain_is_built_without_a_gate_when_the_plugin_is_missing() -> None:
    config = stage_config("stage.in", "stage.out", "Voice", CONTROLS, gate_plugin=None)

    assert "lv2" not in config
    assert "gate:" not in config


def test_descriptions_are_quoted_safely_in_the_config() -> None:
    config = stage_config("stage.in", "stage.out", 'Say "hi"', CONTROLS, gate_plugin=None)

    assert 'node.description = "Say \\"hi\\""' in config


def test_stage_controls_are_sent_with_pw_cli() -> None:
    runner = FakeRunner()

    PwCliStageControl(runner, with_gate=True).set_controls(42, CONTROLS)

    [args] = runner.calls
    assert args[:4] == ["pw-cli", "set-param", "42", "Props"]
    assert args[4] == (
        '{ params = [ "lowcut:Freq" 100.000000 "gain:Mult" 0.500000 '
        '"gate:enabled" 1.000000 "gate:gt" 0.010000 ] }'
    )


def test_gate_controls_are_left_out_without_the_plugin() -> None:
    assert control_values(CONTROLS, with_gate=False) == {"lowcut:Freq": 100.0, "gain:Mult": 0.5}


def test_taps_record_raw_float_stereo_without_autolinking() -> None:
    launcher = FakeLauncher()

    PwRecordTaps(launcher).open("onemic.lesson.tap.mix")

    [args] = launcher.streams
    assert args[0] == "pw-record"
    assert args[args.index("--format") + 1] == "f32"
    assert args[args.index("--target") + 1] == "0"
    assert json.loads(args[args.index("--properties") + 1])["node.autoconnect"] is False
    assert args[-1] == "-"
