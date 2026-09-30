from __future__ import annotations


class AudioError(Exception):
    """A PipeWire tool was missing, timed out, or refused a request.

    Kept separate from ProfileError so the interface can tell "your audio
    system said no" apart from "that name is not allowed".
    """


class ProfileError(ValueError):
    """A mic or input edit that would leave the saved settings invalid."""
