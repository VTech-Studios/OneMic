from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from .errors import ProfileError

MAX_INPUTS = 8
MAX_GAIN = 1.5
MAX_NAME_LENGTH = 40
DEFAULT_GATE_DB = -45.0
MIN_GATE_DB = -60.0
MAX_GATE_DB = -10.0

_ALLOWED_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ()&,.+_-]*")
_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def validate_name(name: str) -> str:
    """Check a mic name before it reaches PipeWire.

    The name becomes the device description that browsers list, passed
    through pactl's quoted module arguments. Quotes and backslashes would
    break out of that quoting, so only plain punctuation is accepted.

    @param name: the name as typed.
    @return: the name without surrounding whitespace.
    @raise ProfileError: if the name is empty, too long, or has unsafe characters.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ProfileError("A mic needs a name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ProfileError(f"Keep the name under {MAX_NAME_LENGTH} characters.")
    if not _ALLOWED_NAME.fullmatch(cleaned):
        raise ProfileError("Use letters, numbers, spaces and ( ) & , . + _ - only.")
    return cleaned


def slugify(name: str) -> str:
    """Turn a display name into the identifier used in node names and files.

    @param name: a validated mic name.
    @return: lowercase letters and digits joined by hyphens.
    """
    return _NOT_SLUG.sub("-", name.lower()).strip("-")


def clamp_gate(threshold_db: float) -> float:
    """Keep a gate threshold where it can do something useful.

    Below -60 dB a gate would never close on a real room, and above -10 dB
    it would chop into normal playing and speech.

    @param threshold_db: the requested threshold in dBFS.
    @return: the threshold limited to MIN_GATE_DB to MAX_GATE_DB.
    """
    return min(max(threshold_db, MIN_GATE_DB), MAX_GATE_DB)


def clamp_gain(gain: float) -> float:
    """Keep a gain within what the volume controls accept.

    Up to 150% is allowed so a quiet source can be lifted, matching the
    ceiling of the desktop's own volume controls.

    @param gain: the requested gain, where 1.0 is unity.
    @return: the gain limited to 0.0 to MAX_GAIN.
    """
    return min(max(gain, 0.0), MAX_GAIN)


@dataclass(frozen=True)
class InputSettings:
    """One signal feeding a mic, and how it is processed on the way.

    The id is generated once and never changes, so renaming or reordering
    inputs never confuses which gain stage belongs to which input.
    """

    id: str
    source: str
    label: str
    gain: float = 1.0
    muted: bool = False
    soloed: bool = False
    low_cut: bool = False
    gate: bool = False
    gate_threshold_db: float = DEFAULT_GATE_DB


@dataclass(frozen=True)
class MicProfile:
    """A named virtual mic and everything needed to rebuild it."""

    name: str
    inputs: tuple[InputSettings, ...] = ()
    gain: float = 1.0
    muted: bool = False

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def input(self, input_id: str) -> InputSettings:
        """Look up one input by id.

        @param input_id: the input's generated id.
        @return: that input's settings.
        @raise ProfileError: if the mic has no such input.
        """
        for settings in self.inputs:
            if settings.id == input_id:
                return settings
        raise ProfileError(f"No input with id {input_id}.")

    def with_input(self, settings: InputSettings) -> MicProfile:
        """Add an input, refusing more than the interface can show.

        @param settings: the new input.
        @return: a copy of the mic with the input appended.
        @raise ProfileError: if the mic is already full.
        """
        if len(self.inputs) >= MAX_INPUTS:
            raise ProfileError(f"A mic can have up to {MAX_INPUTS} inputs.")
        return replace(self, inputs=(*self.inputs, settings))

    def without_input(self, input_id: str) -> MicProfile:
        """Remove an input.

        @param input_id: the input's generated id.
        @return: a copy of the mic without that input.
        """
        return replace(self, inputs=tuple(item for item in self.inputs if item.id != input_id))

    def with_input_gain(self, input_id: str, gain: float) -> MicProfile:
        """Change one input's gain.

        @param input_id: the input's generated id.
        @param gain: the new gain, clamped to the allowed range.
        @return: a copy of the mic with the new gain.
        """
        return self._edit_input(input_id, gain=clamp_gain(gain))

    def with_input_muted(self, input_id: str, muted: bool) -> MicProfile:
        """Mute or unmute one input.

        @param input_id: the input's generated id.
        @param muted: True to silence the input without removing it.
        @return: a copy of the mic with the new mute state.
        """
        return self._edit_input(input_id, muted=muted)

    def with_input_soloed(self, input_id: str, soloed: bool) -> MicProfile:
        """Solo or unsolo one input.

        @param input_id: the input's generated id.
        @param soloed: True to hear this input alongside any other soloed ones only.
        @return: a copy of the mic with the new solo state.
        """
        return self._edit_input(input_id, soloed=soloed)

    def with_input_low_cut(self, input_id: str, low_cut: bool) -> MicProfile:
        """Switch one input's low-cut filter on or off.

        @param input_id: the input's generated id.
        @param low_cut: True to remove rumble below the low-cut frequency.
        @return: a copy of the mic with the new low-cut state.
        """
        return self._edit_input(input_id, low_cut=low_cut)

    def with_input_gate(self, input_id: str, gate: bool) -> MicProfile:
        """Switch one input's noise gate on or off.

        @param input_id: the input's generated id.
        @param gate: True to silence the input whenever it falls below its threshold.
        @return: a copy of the mic with the new gate state.
        """
        return self._edit_input(input_id, gate=gate)

    def with_input_gate_threshold(self, input_id: str, threshold_db: float) -> MicProfile:
        """Move one input's gate threshold.

        @param input_id: the input's generated id.
        @param threshold_db: the level in dBFS the gate opens at, clamped to the allowed range.
        @return: a copy of the mic with the new threshold.
        """
        return self._edit_input(input_id, gate_threshold_db=clamp_gate(threshold_db))

    def is_silenced(self, settings: InputSettings) -> bool:
        """Decide whether an input is heard, taking every input's solo into account.

        Solo works as it does in a DAW: while any input is soloed, only
        soloed inputs are heard. Mute still wins, so a muted input stays
        silent even when soloed.

        @param settings: one of this mic's inputs.
        @return: True if the input should be silent.
        """
        any_soloed = any(item.soloed for item in self.inputs)
        return settings.muted or (any_soloed and not settings.soloed)

    def with_gain(self, gain: float) -> MicProfile:
        """Change the master gain applied to the whole mix.

        @param gain: the new gain, clamped to the allowed range.
        @return: a copy of the mic with the new master gain.
        """
        return replace(self, gain=clamp_gain(gain))

    def with_muted(self, muted: bool) -> MicProfile:
        """Mute or unmute the whole mic, which the far end then hears as silence.

        @param muted: True to silence the mic.
        @return: a copy of the mic with the new mute state.
        """
        return replace(self, muted=muted)

    def renamed(self, name: str) -> MicProfile:
        """Give the mic a new name.

        @param name: the name as typed.
        @return: a copy of the mic with the validated name.
        @raise ProfileError: if the name is not allowed.
        """
        return replace(self, name=validate_name(name))

    def _edit_input(self, input_id: str, **changes: Any) -> MicProfile:
        """Replace some of one input's settings, keeping its place in the list.

        @param input_id: the input's generated id.
        @param changes: the settings to change, by field name.
        @return: a copy of the mic with the edited input.
        @raise ProfileError: if the mic has no such input.
        """
        edited = replace(self.input(input_id), **changes)
        return replace(self, inputs=tuple(edited if item.id == input_id else item for item in self.inputs))
