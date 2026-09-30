import json
from pathlib import Path

from onemic.domain.profile import InputSettings, MicProfile
from onemic.domain.window import Corner, WindowState
from onemic.infrastructure.stores import JsonProfileStore, JsonWindowStateStore

LESSON = MicProfile(
    "Guitar Lesson",
    (
        InputSettings("a1", "REAPER", "REAPER", 0.8, soloed=True),
        InputSettings("b2", "mic2", "Voice", muted=True),
    ),
    gain=0.9,
)


def test_mics_round_trip(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path / "onemic" / "mics.json")

    store.save([LESSON, MicProfile("Stream")], "guitar-lesson")

    assert store.load() == ([LESSON, MicProfile("Stream")], "guitar-lesson")


def test_a_missing_file_means_no_mics(tmp_path: Path) -> None:
    assert JsonProfileStore(tmp_path / "mics.json").load() == ([], None)


def test_a_damaged_file_is_set_aside_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "mics.json"
    path.write_text("{ not json")

    assert JsonProfileStore(path).load() == ([], None)
    assert (tmp_path / "mics.json.broken").read_text() == "{ not json"
    assert not path.exists()


def test_unusable_entries_are_skipped_and_values_clamped(tmp_path: Path) -> None:
    path = tmp_path / "mics.json"
    path.write_text(
        json.dumps(
            {
                "mics": [
                    {"name": 'Bad "quote"'},
                    {"gain": 1.0},
                    {"name": "Loud", "gain": 9, "inputs": [{"id": "x", "source": "s", "gain": -2}]},
                ]
            }
        )
    )

    profiles, selected = JsonProfileStore(path).load()

    assert selected is None
    assert [profile.name for profile in profiles] == ["Loud"]
    assert profiles[0].gain == 1.5
    assert profiles[0].inputs[0] == InputSettings("x", "s", "s", 0.0, False)


def test_saving_leaves_no_temporary_file(tmp_path: Path) -> None:
    JsonProfileStore(tmp_path / "mics.json").save([LESSON], None)

    assert [path.name for path in tmp_path.iterdir()] == ["mics.json"]


def test_window_state_round_trips(tmp_path: Path) -> None:
    store = JsonWindowStateStore(tmp_path / "window.json")
    state = WindowState(Corner.TOP_LEFT, "DP-2", expanded=True)

    store.save(state)

    assert store.load() == state


def test_window_state_defaults_when_missing_or_invalid(tmp_path: Path) -> None:
    path = tmp_path / "window.json"
    assert JsonWindowStateStore(path).load() == WindowState()

    path.write_text(json.dumps({"corner": "middle", "screen": "", "expanded": True}))

    assert JsonWindowStateStore(path).load() == WindowState(Corner.BOTTOM_RIGHT, None, expanded=True)
