from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import replace

from ..domain.errors import ProfileError
from ..domain.profile import InputSettings, MicProfile, validate_name
from ..domain.sources import AudioSource
from ..ports import ProfileStore

DEFAULT_NAME = "My Mic"


def new_input_id() -> str:
    """Generate an id for a new input.

    @return: eight random hex characters, unique within any realistic mic.
    """
    return secrets.token_hex(4)


class ProfileLibrary:
    """The saved mics, which one is selected, and every edit to them.

    Edits only change memory. The caller decides when to save, so a slider
    being dragged does not rewrite the file for every step.
    """

    def __init__(self, store: ProfileStore, new_id: Callable[[], str] = new_input_id) -> None:
        self._store = store
        self._new_id = new_id
        profiles, selected = store.load()
        self._profiles = profiles or [MicProfile(DEFAULT_NAME)]
        self._selected = selected if self._find(selected) else self._profiles[0].slug

    @property
    def profiles(self) -> tuple[MicProfile, ...]:
        return tuple(self._profiles)

    @property
    def selected(self) -> MicProfile:
        profile = self._find(self._selected)
        if profile is None:
            raise ProfileError("The selected mic no longer exists.")
        return profile

    def get(self, slug: str) -> MicProfile:
        """Look up a mic by slug.

        @param slug: the mic's slug.
        @return: the mic.
        @raise ProfileError: if no mic has that slug.
        """
        profile = self._find(slug)
        if profile is None:
            raise ProfileError("That mic no longer exists.")
        return profile

    def select(self, slug: str) -> MicProfile:
        """Make a mic the one shown and edited.

        @param slug: the mic's slug.
        @return: the newly selected mic.
        """
        profile = self.get(slug)
        self._selected = slug
        return profile

    def create(self, name: str) -> MicProfile:
        """Add an empty mic and select it.

        @param name: the name as typed.
        @return: the new mic.
        @raise ProfileError: if the name is invalid or taken.
        """
        profile = MicProfile(self._unused_name(name))
        self._profiles.append(profile)
        return self.select(profile.slug)

    def duplicate(self, slug: str, name: str) -> MicProfile:
        """Copy a mic under a new name and select the copy.

        Inputs get fresh ids, so the copy's gain stages can never be confused
        with the original's.

        @param slug: the mic to copy.
        @param name: the copy's name as typed.
        @return: the copy.
        @raise ProfileError: if the name is invalid or taken.
        """
        original = self.get(slug)
        inputs = tuple(replace(item, id=self._new_id()) for item in original.inputs)
        copy = replace(original, name=self._unused_name(name), inputs=inputs)
        self._profiles.append(copy)
        return self.select(copy.slug)

    def rename(self, slug: str, name: str) -> MicProfile:
        """Rename a mic, keeping its place in the list and its selection.

        @param slug: the mic to rename.
        @param name: the new name as typed.
        @return: the renamed mic.
        @raise ProfileError: if the name is invalid or taken by another mic.
        """
        profile = self.get(slug)
        renamed = profile.renamed(self._unused_name(name, ignoring=slug))
        self._profiles[self._profiles.index(profile)] = renamed
        if self._selected == slug:
            self._selected = renamed.slug
        return renamed

    def delete(self, slug: str) -> None:
        """Delete a mic, selecting another if it was selected.

        @param slug: the mic to delete.
        @raise ProfileError: if it is the only mic, since the window always shows one.
        """
        if len(self._profiles) == 1:
            raise ProfileError("Keep at least one mic.")
        self._profiles.remove(self.get(slug))
        if self._selected == slug:
            self._selected = self._profiles[0].slug

    def update(self, profile: MicProfile) -> MicProfile:
        """Store an edited version of an existing mic.

        @param profile: the edited mic, matched to the original by slug.
        @return: the stored mic.
        """
        original = self.get(profile.slug)
        self._profiles[self._profiles.index(original)] = profile
        return profile

    def new_input(self, source: AudioSource) -> InputSettings:
        """Describe a source as a new input at unity gain, with a fresh id.

        @param source: the source picked from the graph.
        @return: settings ready to add to a mic.
        """
        return InputSettings(id=self._new_id(), source=source.name, label=source.description)

    def save(self) -> None:
        """Write every mic and the selection to the store."""
        self._store.save(self._profiles, self._selected)

    def _find(self, slug: str | None) -> MicProfile | None:
        return next((profile for profile in self._profiles if profile.slug == slug), None)

    def _unused_name(self, name: str, ignoring: str | None = None) -> str:
        """Validate a name and check no other mic would share its slug.

        Two mics with one slug would share PipeWire node names, and each
        would tear down the other.

        @param name: the name as typed.
        @param ignoring: a slug that may keep its own name, when renaming.
        @return: the validated name.
        @raise ProfileError: if the name is invalid or taken.
        """
        cleaned = validate_name(name)
        slug = MicProfile(cleaned).slug
        if not slug:
            raise ProfileError("Include at least one letter or number in the name.")
        if slug != ignoring and self._find(slug):
            raise ProfileError(f"A mic called {cleaned} already exists.")
        return cleaned
