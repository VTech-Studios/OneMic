from __future__ import annotations

from collections.abc import Callable, Collection, Sequence

from ..domain.errors import ProfileError
from ..domain.profile import MicProfile
from ..services.library import ProfileLibrary

LIVE_RENAME = "Stop the mic before renaming it. Call apps would lose the device mid-call."
LIVE_DELETE = "Stop the mic before deleting it."


class LibraryMicActions:
    """The mic manager's actions, turning rule violations into messages.

    The live mic cannot be renamed or deleted, because its name is part of
    every PipeWire node it owns, and changing it would drop the call.
    """

    def __init__(self, library: ProfileLibrary, protected: Callable[[], Collection[str]]) -> None:
        self._library = library
        self._protected = protected

    def list_mics(self) -> Sequence[MicProfile]:
        """List every saved mic, in display order.

        @return: the mics.
        """
        return self._library.profiles

    def create_mic(self, name: str) -> str | None:
        """Add an empty mic.

        @param name: the name as typed.
        @return: an error message, or None on success.
        """
        return self._attempt(lambda: self._library.create(name))

    def duplicate_mic(self, slug: str, name: str) -> str | None:
        """Copy a mic under a new name.

        @param slug: the mic to copy.
        @param name: the copy's name as typed.
        @return: an error message, or None on success.
        """
        return self._attempt(lambda: self._library.duplicate(slug, name))

    def rename_mic(self, slug: str, name: str) -> str | None:
        """Rename a mic that is not live.

        @param slug: the mic to rename.
        @param name: the new name as typed.
        @return: an error message, or None on success.
        """
        if slug in self._protected():
            return LIVE_RENAME
        return self._attempt(lambda: self._library.rename(slug, name))

    def delete_mic(self, slug: str) -> str | None:
        """Delete a mic that is not live.

        @param slug: the mic to delete.
        @return: an error message, or None on success.
        """
        if slug in self._protected():
            return LIVE_DELETE
        return self._attempt(lambda: self._library.delete(slug))

    @staticmethod
    def _attempt(action: Callable[[], object]) -> str | None:
        try:
            action()
        except ProfileError as error:
            return str(error)
        return None
