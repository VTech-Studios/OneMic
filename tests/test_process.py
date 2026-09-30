from pathlib import Path

import pytest

from onemic.domain.errors import AudioError
from onemic.infrastructure.process import SubprocessLauncher, SubprocessRunner


def test_runner_returns_standard_output() -> None:
    assert SubprocessRunner().run(["printf", "hello"]) == "hello"


def test_runner_reports_a_missing_program() -> None:
    with pytest.raises(AudioError, match="not installed"):
        SubprocessRunner().run(["onemic-no-such-program"])


def test_runner_reports_a_failing_command_with_its_error() -> None:
    with pytest.raises(AudioError, match="boom"):
        SubprocessRunner().run(["sh", "-c", "echo boom >&2; exit 3"])


def test_runner_gives_up_after_the_timeout() -> None:
    with pytest.raises(AudioError, match="did not answer"):
        SubprocessRunner().run(["sleep", "5"], timeout=0.1)


def test_streams_deliver_output_then_end() -> None:
    stream = SubprocessLauncher().open_stream(["printf", "abcdef"])

    assert stream.read(3) == b"abc"
    assert stream.read(10) == b"def"
    assert stream.read(10) == b""
    stream.close()


def test_closing_a_stream_stops_the_helper() -> None:
    stream = SubprocessLauncher().open_stream(["sleep", "30"])

    stream.close()

    assert stream.read(1) == b""


def test_detached_helpers_can_be_terminated_when_they_are_the_expected_program() -> None:
    launcher = SubprocessLauncher()
    pid = launcher.spawn_detached(["sleep", "30"])

    launcher.terminate(pid, "sleep")

    assert not Path(f"/proc/{pid}").exists()


IMPOSSIBLE_PID = 2**23


def test_terminate_refuses_a_process_running_something_else(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / str(IMPOSSIBLE_PID)).mkdir()
    (tmp_path / str(IMPOSSIBLE_PID) / "comm").write_text("pipewire-pulse\n")

    SubprocessLauncher(proc=tmp_path).terminate(IMPOSSIBLE_PID, "pw-loopback")

    assert "it is not pw-loopback" in caplog.text


def test_terminate_ignores_a_process_that_has_gone(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    SubprocessLauncher(proc=tmp_path).terminate(IMPOSSIBLE_PID, "pw-loopback")

    assert "Not stopping" in caplog.text


def test_starting_a_missing_program_is_an_audio_error() -> None:
    with pytest.raises(AudioError, match="could not be started"):
        SubprocessLauncher().spawn_detached(["onemic-no-such-program"])


def test_helpers_that_exit_on_their_own_are_reaped() -> None:
    launcher = SubprocessLauncher()
    first = launcher.spawn_detached(["true"])
    import time

    time.sleep(0.2)
    launcher.spawn_detached(["true"])

    assert first not in launcher._children
