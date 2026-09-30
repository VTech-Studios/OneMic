import itertools

import pytest

from onemic.domain.errors import ProfileError
from onemic.domain.profile import InputSettings, MicProfile
from onemic.domain.sources import AudioSource, SourceKind
from onemic.services.library import DEFAULT_NAME, ProfileLibrary, new_input_id
from tests.fakes import InMemoryProfileStore

LESSON = MicProfile("Guitar Lesson", (InputSettings("a1", "REAPER", "REAPER"),))
STREAM = MicProfile("Stream")


def library(*profiles: MicProfile, selected: str | None = None) -> ProfileLibrary:
    ids = (f"id{n}" for n in itertools.count())
    return ProfileLibrary(InMemoryProfileStore(profiles, selected), new_id=lambda: next(ids))


def test_an_empty_store_starts_with_one_default_mic() -> None:
    assert [profile.name for profile in library().profiles] == [DEFAULT_NAME]


def test_the_saved_selection_is_restored_and_a_missing_one_falls_back() -> None:
    assert library(LESSON, STREAM, selected="stream").selected == STREAM
    assert library(LESSON, STREAM, selected="gone").selected == LESSON


def test_creating_a_mic_selects_it() -> None:
    lib = library(LESSON)

    created = lib.create("  Band Practice ")

    assert created.name == "Band Practice"
    assert lib.selected == created


@pytest.mark.parametrize("name", ["guitar lesson", "Guitar-Lesson", "...", 'Bad"'])
def test_names_that_clash_or_are_invalid_are_refused(name: str) -> None:
    with pytest.raises(ProfileError):
        library(LESSON).create(name)


def test_duplicating_copies_settings_with_fresh_input_ids() -> None:
    lib = library(LESSON)

    copy = lib.duplicate("guitar-lesson", "Lesson Two")

    assert copy.inputs[0].source == "REAPER"
    assert copy.inputs[0].id != "a1"
    assert lib.selected == copy


def test_renaming_keeps_position_and_selection() -> None:
    lib = library(LESSON, STREAM, selected="guitar-lesson")

    lib.rename("guitar-lesson", "Lesson")

    assert [profile.name for profile in lib.profiles] == ["Lesson", "Stream"]
    assert lib.selected.name == "Lesson"


def test_a_mic_may_be_renamed_to_a_different_case_of_its_own_name() -> None:
    assert library(LESSON).rename("guitar-lesson", "GUITAR LESSON").name == "GUITAR LESSON"


def test_renaming_onto_another_mic_is_refused() -> None:
    with pytest.raises(ProfileError):
        library(LESSON, STREAM).rename("stream", "Guitar Lesson")


def test_deleting_the_selected_mic_selects_another() -> None:
    lib = library(LESSON, STREAM, selected="stream")

    lib.delete("stream")

    assert lib.selected == LESSON


def test_the_last_mic_cannot_be_deleted() -> None:
    with pytest.raises(ProfileError):
        library(LESSON).delete("guitar-lesson")


def test_unknown_mics_are_refused() -> None:
    with pytest.raises(ProfileError):
        library(LESSON).select("nope")


def test_updates_replace_the_mic_with_the_same_slug() -> None:
    lib = library(LESSON)

    lib.update(LESSON.with_gain(0.5))

    assert lib.selected.gain == 0.5


def test_new_inputs_get_fresh_ids_and_the_source_description() -> None:
    source = AudioSource("alsa_input.mic2", "Scarlett Mic 2", SourceKind.MICROPHONE)

    assert library().new_input(source) == InputSettings("id0", "alsa_input.mic2", "Scarlett Mic 2")


def test_saving_writes_every_mic_and_the_selection() -> None:
    store = InMemoryProfileStore([LESSON, STREAM], "stream")
    lib = ProfileLibrary(store)

    lib.select("guitar-lesson")
    lib.save()

    assert store.selected == "guitar-lesson"
    assert store.profiles == [LESSON, STREAM]


def test_generated_ids_are_short_and_distinct() -> None:
    ids = {new_input_id() for _ in range(100)}

    assert len(ids) == 100
    assert all(len(value) == 8 for value in ids)
