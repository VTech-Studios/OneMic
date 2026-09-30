import pytest

from onemic.domain.errors import ProfileError
from onemic.domain.profile import (
    MAX_GAIN,
    MAX_INPUTS,
    InputSettings,
    MicProfile,
    clamp_gain,
    slugify,
    validate_name,
)

GUITAR = InputSettings("g1", "REAPER", "REAPER")
VOICE = InputSettings("v1", "mic2", "Voice", gain=0.8)


def test_valid_names_are_trimmed() -> None:
    assert validate_name("  Guitar Lesson (2)  ") == "Guitar Lesson (2)"


@pytest.mark.parametrize("name", ["", "   ", 'Quote"s', "Back\\slash", "It's", "x" * 41, "-leading"])
def test_unsafe_or_empty_names_are_refused(name: str) -> None:
    with pytest.raises(ProfileError):
        validate_name(name)


@pytest.mark.parametrize(
    ("name", "slug"), [("Guitar Lesson", "guitar-lesson"), ("Mic & Amp (2)", "mic-amp-2"), ("A.B_C", "a-b-c")]
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug


def test_gain_is_clamped() -> None:
    assert clamp_gain(-1.0) == 0.0
    assert clamp_gain(9.0) == MAX_GAIN
    assert clamp_gain(0.7) == 0.7


def test_inputs_can_be_added_up_to_the_limit() -> None:
    profile = MicProfile("Full")
    for index in range(MAX_INPUTS):
        profile = profile.with_input(InputSettings(str(index), f"source{index}", "x"))

    with pytest.raises(ProfileError):
        profile.with_input(GUITAR)


def test_input_edits_change_only_that_input() -> None:
    profile = MicProfile("Lesson", (GUITAR, VOICE))

    edited = profile.with_input_gain("g1", 0.5).with_input_muted("v1", True)

    assert edited.input("g1").gain == 0.5
    assert edited.input("v1").muted
    assert edited.input("v1").gain == 0.8
    assert profile.input("g1").gain == 1.0


def test_input_gain_is_clamped() -> None:
    assert MicProfile("L", (GUITAR,)).with_input_gain("g1", 5.0).input("g1").gain == MAX_GAIN


def test_removing_an_input() -> None:
    assert MicProfile("L", (GUITAR, VOICE)).without_input("g1").inputs == (VOICE,)


def test_unknown_input_ids_are_refused() -> None:
    with pytest.raises(ProfileError):
        MicProfile("L").input("nope")


def test_master_gain_and_mute() -> None:
    profile = MicProfile("L").with_gain(2.0).with_muted(True)

    assert profile.gain == MAX_GAIN
    assert profile.muted


def test_renaming_validates_and_changes_the_slug() -> None:
    renamed = MicProfile("Old").renamed(" New Name ")

    assert renamed.name == "New Name"
    assert renamed.slug == "new-name"
    with pytest.raises(ProfileError):
        renamed.renamed('bad"name')
