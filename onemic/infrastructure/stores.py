from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..domain.profile import (
    DEFAULT_GATE_DB,
    InputSettings,
    MicProfile,
    clamp_gain,
    clamp_gate,
    validate_name,
)
from ..domain.window import Corner, WindowState

FORMAT_VERSION = 1

log = logging.getLogger(__name__)


def write_atomically(path: Path, document: Mapping[str, Any]) -> None:
    """Write JSON so a crash mid-write never leaves a half-written file.

    The new content goes to a temporary file first, then replaces the old
    file in one step, which the filesystem guarantees is all or nothing.

    @param path: the file to replace.
    @param document: the JSON-compatible content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_document(path: Path) -> Mapping[str, Any] | None:
    """Read a JSON settings file, setting aside one that cannot be read.

    A damaged file is renamed rather than overwritten, so the next save
    cannot destroy settings the user might still recover by hand.

    @param path: the file to read.
    @return: the decoded object, or None if the file is missing or damaged.
    """
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if isinstance(document, Mapping):
        return document
    broken = path.with_suffix(f"{path.suffix}.broken")
    path.replace(broken)
    log.warning("%s could not be read and was moved to %s", path, broken)
    return None


def _input_to_json(settings: InputSettings) -> dict[str, Any]:
    return {
        "id": settings.id,
        "source": settings.source,
        "label": settings.label,
        "gain": settings.gain,
        "muted": settings.muted,
        "soloed": settings.soloed,
        "low_cut": settings.low_cut,
        "gate": settings.gate,
        "gate_threshold_db": settings.gate_threshold_db,
    }


def _input_from_json(item: Mapping[str, Any]) -> InputSettings:
    return InputSettings(
        id=str(item["id"]),
        source=str(item["source"]),
        label=str(item.get("label") or item["source"]),
        gain=clamp_gain(float(item.get("gain", 1.0))),
        muted=bool(item.get("muted", False)),
        soloed=bool(item.get("soloed", False)),
        low_cut=bool(item.get("low_cut", False)),
        gate=bool(item.get("gate", False)),
        gate_threshold_db=clamp_gate(float(item.get("gate_threshold_db", DEFAULT_GATE_DB))),
    )


def profile_to_json(profile: MicProfile) -> dict[str, Any]:
    """Convert a mic to plain JSON types.

    @param profile: the mic to save.
    @return: a dictionary that json.dumps accepts.
    """
    return {
        "name": profile.name,
        "gain": profile.gain,
        "muted": profile.muted,
        "inputs": [_input_to_json(item) for item in profile.inputs],
    }


def profile_from_json(item: Mapping[str, Any]) -> MicProfile:
    """Rebuild a mic from saved JSON, checking values that may have been edited by hand.

    The name is validated again because it reaches pactl, and a hand-edited
    file is as untrusted as anything typed into the interface.

    @param item: one entry from the saved list.
    @return: the mic.
    @raise KeyError: if a required field is missing.
    @raise ProfileError: if the name is not allowed.
    """
    return MicProfile(
        name=validate_name(str(item["name"])),
        inputs=tuple(_input_from_json(entry) for entry in item.get("inputs", [])),
        gain=clamp_gain(float(item.get("gain", 1.0))),
        muted=bool(item.get("muted", False)),
    )


class JsonProfileStore:
    """Keeps every mic in one JSON file under the user's config directory."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def location(self) -> Path:
        return self._path

    def load(self) -> tuple[list[MicProfile], str | None]:
        """Read every saved mic, skipping any entry too damaged to use.

        @return: the mics, and the slug of the one last selected.
        """
        document = read_document(self._path) or {}
        profiles = []
        for item in document.get("mics", []):
            try:
                profiles.append(profile_from_json(item))
            except (KeyError, TypeError, ValueError):
                log.warning("Skipped a saved mic that could not be read: %r", item)
        selected = document.get("selected")
        return profiles, str(selected) if selected else None

    def save(self, profiles: Sequence[MicProfile], selected: str | None) -> None:
        """Replace the saved mics.

        @param profiles: every mic, in display order.
        @param selected: the slug of the mic to reopen next time.
        """
        write_atomically(
            self._path,
            {
                "version": FORMAT_VERSION,
                "selected": selected,
                "mics": [profile_to_json(profile) for profile in profiles],
            },
        )


class JsonWindowStateStore:
    """Remembers the window's corner, screen and size in a small JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> WindowState:
        """Read where the window was left.

        @return: the saved state, or the defaults if none was saved or it is unreadable.
        """
        document = read_document(self._path) or {}
        try:
            corner = Corner(document.get("corner", Corner.BOTTOM_RIGHT.value))
        except ValueError:
            corner = Corner.BOTTOM_RIGHT
        screen = document.get("screen")
        return WindowState(
            corner=corner,
            screen=str(screen) if screen else None,
            expanded=bool(document.get("expanded", False)),
        )

    def save(self, state: WindowState) -> None:
        """Remember where the window is.

        @param state: the window's corner, screen and size.
        """
        write_atomically(
            self._path,
            {"corner": state.corner.value, "screen": state.screen, "expanded": state.expanded},
        )
