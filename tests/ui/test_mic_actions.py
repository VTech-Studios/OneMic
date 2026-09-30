from onemic.domain.profile import MicProfile
from onemic.services.library import ProfileLibrary
from onemic.ui.mic_actions import LIVE_DELETE, LIVE_RENAME, LibraryMicActions
from tests.fakes import InMemoryProfileStore


def actions(live: str | None = None) -> tuple[LibraryMicActions, ProfileLibrary]:
    library = ProfileLibrary(InMemoryProfileStore([MicProfile("Lesson"), MicProfile("Stream")]))
    return LibraryMicActions(library, lambda: {live} if live else set()), library


def test_successful_actions_return_no_error() -> None:
    subject, _ = actions()

    assert subject.create_mic("Band") is None
    assert subject.duplicate_mic("band", "Band Two") is None
    assert subject.rename_mic("band-two", "Band 2") is None
    assert subject.delete_mic("band") is None
    assert [profile.name for profile in subject.list_mics()] == ["Lesson", "Stream", "Band 2"]


def test_rule_violations_come_back_as_messages() -> None:
    subject, _ = actions()

    assert subject.create_mic("lesson") == "A mic called lesson already exists."


def test_the_live_mic_cannot_be_renamed_or_deleted() -> None:
    subject, library = actions(live="lesson")

    assert subject.rename_mic("lesson", "New") == LIVE_RENAME
    assert subject.delete_mic("lesson") == LIVE_DELETE
    assert library.get("lesson").name == "Lesson"
