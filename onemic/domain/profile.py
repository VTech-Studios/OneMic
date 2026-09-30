from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .errors import ProfileError

MAX_INPUTS = 8
MAX_GAIN = 1.5
MAX_NAME_LENGTH = 40

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
    """One signal feeding a mic, and how loud it should be.

    The id is generated once and never changes, so renaming or reordering
    inputs never confuses which gain stage belongs to which input.
    """

    id: str
    source: str
    label: str
    gain: float = 1.0
    muted: bool = False


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
        return self._replace_input(replace(self.input(input_id), gain=clamp_gain(gain)))

    def with_input_muted(self, input_id: str, muted: bool) -> MicProfile:
        """Mute or unmute one input.

        @param input_id: the input's generated id.
        @param muted: True to silence the input without removing it.
        @return: a copy of the mic with the new mute state.
        """
        return self._replace_input(replace(self.input(input_id), muted=muted))

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

    def _replace_input(self, settings: InputSettings) -> MicProfile:
        return replace(
            self, inputs=tuple(settings if item.id == settings.id else item for item in self.inputs)
        )
