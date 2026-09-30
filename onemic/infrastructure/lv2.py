from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

LSP_GATE_URI = "http://lsp-plug.in/plugins/lv2/gate_mono"
LSP_BUNDLE = "lsp-plugins.lv2"
LSP_GATE_FILE = "gate_mono.ttl"
SYSTEM_LV2_DIRS = ("/usr/lib/lv2", "/usr/local/lib/lv2")


def lv2_dirs(environment: Mapping[str, str]) -> list[Path]:
    """List the directories LV2 hosts search, in the order they search them.

    @param environment: the process environment, for LV2_PATH and HOME.
    @return: the search directories.
    """
    configured = environment.get("LV2_PATH")
    if configured:
        return [Path(entry).expanduser() for entry in configured.split(":") if entry]
    home = Path(environment.get("HOME", "~")).expanduser()
    return [home / ".lv2", *(Path(entry) for entry in SYSTEM_LV2_DIRS)]


def find_lsp_gate(environment: Mapping[str, str]) -> str | None:
    """Find the LSP mono gate, which OneMic uses for its noise gate.

    PipeWire has a built-in gate, but the one in current releases measures
    its own output, so once closed it never opens again. The LSP gate is a
    well-tested plugin, and asking for it only when it is installed keeps
    everything else working without it.

    @param environment: the process environment.
    @return: the plugin's URI, or None if lsp-plugins is not installed.
    """
    for directory in lv2_dirs(environment):
        if (directory / LSP_BUNDLE / LSP_GATE_FILE).is_file():
            return LSP_GATE_URI
    return None
