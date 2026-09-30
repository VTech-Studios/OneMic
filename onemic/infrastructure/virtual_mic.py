from __future__ import annotations

from ..ports import CommandRunner


class PactlVirtualMic:
    """Creates virtual mics as null sinks loaded into pipewire-pulse.

    A null sink with the Audio/Source/Virtual class is the simplest virtual
    microphone PipeWire offers: whatever is linked into it can be recorded
    like a real mic. Loading it through pipewire-pulse keeps it alive after
    this application exits, until it is removed or PipeWire restarts.
    """

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def create(self, node_name: str, description: str) -> None:
        """Create the device that call applications list as a microphone.

        @param node_name: the stable node name.
        @param description: the name shown in device lists, already validated
            to contain no quotes, because it is embedded in quoted module arguments.
        """
        self._runner.run(
            [
                "pactl",
                "load-module",
                "module-null-sink",
                "media.class=Audio/Source/Virtual",
                f"sink_name={node_name}",
                "channel_map=front-left,front-right",
                f"sink_properties='device.description=\"{description}\"'",
            ]
        )

    def remove(self, node_name: str) -> None:
        """Unload every module that created this device.

        More than one can exist if a previous run was interrupted between
        loading and recording the module, so all of them are removed.

        @param node_name: the stable node name given to create.
        """
        for module_id in self._module_ids(node_name):
            self._runner.run(["pactl", "unload-module", module_id])

    def _module_ids(self, node_name: str) -> list[str]:
        listing = self._runner.run(["pactl", "list", "short", "modules"])
        wanted = f"sink_name={node_name}"
        return [
            fields[0]
            for fields in (line.split() for line in listing.splitlines())
            if len(fields) > 2 and fields[1] == "module-null-sink" and wanted in fields[2:]
        ]
