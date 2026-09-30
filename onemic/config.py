from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED_TOOLS = ("pw-dump", "pw-link", "pw-loopback", "pw-record", "pactl", "wpctl")


@dataclass(frozen=True)
class Config:
    """Where OneMic keeps its files.

    Built from the environment rather than read from globals, so tests can
    point every path at a temporary directory.
    """

    config_dir: Path
    runtime_dir: Path

    @property
    def profiles_path(self) -> Path:
        return self.config_dir / "mics.json"

    @property
    def window_path(self) -> Path:
        return self.config_dir / "window.json"

    @property
    def lock_path(self) -> Path:
        return self.runtime_dir / "onemic.lock"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> Config:
        """Follow the XDG base directory rules, like other desktop applications.

        @param environment: the process environment.
        @return: the paths to use.
        """
        home = Path(environment.get("HOME", "~")).expanduser()
        config_home = Path(environment.get("XDG_CONFIG_HOME") or home / ".config")
        runtime = Path(environment.get("XDG_RUNTIME_DIR") or config_home)
        return cls(config_dir=config_home / "onemic", runtime_dir=runtime)
