from __future__ import annotations

import json
from pathlib import Path

from ..domain.stage import STAGE_PROGRAM, StageControls
from ..ports import CommandRunner, ProcessLauncher


def node_properties(name: str, description: str) -> str:
    """Build the properties for a node OneMic links by hand.

    Autoconnect is switched off, or WirePlumber would link the node to the
    default devices on its own, sending a mic straight to the speakers.
    The result is JSON, which PipeWire accepts, so any character in the
    description is safely quoted.

    @param name: the node name.
    @param description: the name shown in patchbays.
    @return: the properties as a JSON object.
    """
    return json.dumps({"node.name": name, "node.description": description, "node.autoconnect": False})


GATE_ATTACK_MS = 5.0
GATE_HOLD_MS = 50.0
GATE_RELEASE_MS = 150.0
GATE_FLOOR = 0.000251


def control_values(controls: StageControls, with_gate: bool) -> dict[str, float]:
    """Name each control the way the filter chain addresses it.

    @param controls: the values to send.
    @param with_gate: False when the chain was built without a gate.
    @return: control values keyed by "node:control".
    """
    values = {"lowcut:Freq": controls.low_cut_hz, "gain:Mult": controls.multiplier}
    if with_gate:
        values |= {"gate:enabled": 1.0 if controls.gate_on else 0.0, "gate:gt": controls.gate_threshold}
    return values


def _gate_node(gate_plugin: str | None, controls: StageControls) -> str:
    """Describe the gate, which is left out when its plugin is not installed.

    Attack is quick so the first syllable or pick attack is not lost, and
    hold and release are long enough not to chop a guitar's sustain. A
    closed gate cuts by 72 dB, the most the plugin allows, which is silence
    on a call.

    @param gate_plugin: the gate's LV2 URI, or None.
    @param controls: the starting values.
    @return: the node's entry for the filter graph, or nothing.
    """
    if gate_plugin is None:
        return ""
    values = control_values(controls, with_gate=True)
    return f"""
          {{ type = lv2 name = gate plugin = {json.dumps(gate_plugin)}
             control = {{
               "enabled" = {values["gate:enabled"]:.0f} "gt" = {values["gate:gt"]:.6f} "gr" = {GATE_FLOOR}
               "at" = {GATE_ATTACK_MS} "hold" = {GATE_HOLD_MS} "rt" = {GATE_RELEASE_MS}
             }} }}"""


def stage_config(
    capture_name: str, playback_name: str, description: str, controls: StageControls, gate_plugin: str | None
) -> str:
    """Write the PipeWire configuration for one gain stage.

    The chain runs low-cut, then gain, then gate, so the gate compares its
    threshold with the level after the input's volume, which is the level
    the meter shows. PipeWire runs the chain once per channel.

    @param capture_name: node name for the side that receives the source.
    @param playback_name: node name for the side that feeds the mic.
    @param description: the name shown in patchbays such as qpwgraph.
    @param controls: the starting values.
    @param gate_plugin: the gate's LV2 URI, or None to build the chain without a gate.
    @return: the configuration, in PipeWire's JSON-like format.
    """
    values = control_values(controls, with_gate=False)
    gate_link = '{ output = "gain:Out" input = "gate:in" }' if gate_plugin else ""
    return f"""context.properties = {{ log.level = 0 }}
context.spa-libs = {{
  audio.convert.* = audioconvert/libspa-audioconvert
  support.* = support/libspa-support
}}
context.modules = [
  {{ name = libpipewire-module-protocol-native }}
  {{ name = libpipewire-module-client-node }}
  {{ name = libpipewire-module-adapter }}
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = {json.dumps(description)}
      audio.channels = 2
      audio.position = [ FL FR ]
      filter.graph = {{
        nodes = [
          {{ type = builtin name = lowcut label = bq_highpass control = {{ "Freq" = {
        values["lowcut:Freq"]:.6f} }} }}
          {{ type = builtin name = gain label = linear control = {{ "Mult" = {values["gain:Mult"]:.6f} }} }}{
        _gate_node(gate_plugin, controls)
    }
        ]
        links = [
          {{ output = "lowcut:Out" input = "gain:In" }}
          {gate_link}
        ]
      }}
      capture.props = {node_properties(capture_name, description)}
      playback.props = {node_properties(playback_name, f"{description} (out)")}
    }}
  }}
]
"""


class FilterChainStages:
    """Runs each gain stage as its own PipeWire filter chain process.

    A link has no volume or processing of its own. A filter chain sits
    between the source and the mic, so each input gets a low-cut, a gain
    and a gate without changing the source for any other application, such
    as a DAW recording the same mic. Each chain is a separate process, so
    it keeps running if the window closes while the mic is live.
    """

    def __init__(self, launcher: ProcessLauncher, config_dir: Path, gate_plugin: str | None) -> None:
        self._launcher = launcher
        self._config_dir = config_dir
        self._gate_plugin = gate_plugin

    def start(self, capture_name: str, playback_name: str, description: str, controls: StageControls) -> None:
        """Write a stage's configuration and start it.

        @param capture_name: node name for the side that receives the source.
        @param playback_name: node name for the side that feeds the mic.
        @param description: the name shown in patchbays.
        @param controls: the starting values.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)
        path = self._config_dir / f"{capture_name}.conf"
        config = stage_config(capture_name, playback_name, description, controls, self._gate_plugin)
        path.write_text(config, encoding="utf-8")
        self._launcher.spawn_detached([STAGE_PROGRAM, "-c", str(path)])


class PwCliStageControl:
    """Changes a running stage's controls through pw-cli, without restarting it."""

    def __init__(self, runner: CommandRunner, with_gate: bool) -> None:
        self._runner = runner
        self._with_gate = with_gate

    def set_controls(self, node_id: int, controls: StageControls) -> None:
        """Send new control values to a stage's filter chain.

        @param node_id: the id of the stage's capture node, which owns the chain.
        @param controls: the values to send.
        """
        pairs = " ".join(
            f"{json.dumps(name)} {value:.6f}"
            for name, value in control_values(controls, self._with_gate).items()
        )
        self._runner.run(["pw-cli", "set-param", str(node_id), "Props", f"{{ params = [ {pairs} ] }}"])
