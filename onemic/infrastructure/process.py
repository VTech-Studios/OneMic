from __future__ import annotations

import contextlib
import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import IO

from ..domain.errors import AudioError

STOP_GRACE_SECONDS = 2.0

log = logging.getLogger(__name__)


def reap(process: subprocess.Popen[bytes]) -> None:
    """Wait for a process that was asked to stop, killing it if it will not.

    Waiting collects its exit status, so no zombie process is left behind.

    @param process: a process that has already been sent SIGTERM.
    """
    try:
        process.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class SubprocessRunner:
    """Runs short PipeWire tools and turns every failure into an AudioError.

    Callers only ever handle one exception type, whatever went wrong.
    """

    def run(self, args: Sequence[str], timeout: float = 5.0) -> str:
        """Run a command to completion.

        @param args: the program and its arguments, never passed through a shell.
        @param timeout: seconds before the command is abandoned.
        @return: the command's standard output.
        @raise AudioError: if the command is missing, times out, or fails.
        """
        try:
            result = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError as error:
            raise AudioError(f"{args[0]} is not installed") from error
        except subprocess.TimeoutExpired as error:
            raise AudioError(f"{args[0]} did not answer within {timeout:g} s") from error
        if result.returncode != 0:
            raise AudioError(f"{' '.join(args)}: {result.stderr.strip() or 'failed'}")
        return result.stdout


class PipeStream:
    """The standard output of a running helper, closed by stopping the helper.

    Closing terminates the process first, so a reader blocked on read()
    wakes with end of stream instead of hanging.
    """

    def __init__(self, process: subprocess.Popen[bytes], output: IO[bytes]) -> None:
        self._process = process
        self._output = output

    def read(self, size: int) -> bytes:
        """Block until a chunk of output arrives.

        @param size: the number of bytes wanted.
        @return: up to size bytes, or an empty result once the helper has exited.
        """
        try:
            return self._output.read(size)
        except (OSError, ValueError):
            return b""

    def close(self) -> None:
        """Stop the helper and release its pipe."""
        self._process.terminate()
        reap(self._process)
        self._output.close()


class SubprocessLauncher:
    """Starts long-running PipeWire helpers."""

    def __init__(self, proc: Path = Path("/proc")) -> None:
        self._children: dict[int, subprocess.Popen[bytes]] = {}
        self._proc = proc

    def spawn_detached(self, args: Sequence[str]) -> int:
        """Start a helper in its own session.

        A separate session means closing the window, or the terminal it was
        started from, does not stop a mic the user chose to leave live.

        @param args: the program and its arguments.
        @return: the new process id.
        @raise AudioError: if the program cannot be started.
        """
        self._reap_exited()
        process = self._popen(args, subprocess.DEVNULL, detached=True)
        self._children[process.pid] = process
        return process.pid

    def open_stream(self, args: Sequence[str]) -> PipeStream:
        """Start a helper whose standard output is read continuously.

        @param args: the program and its arguments.
        @return: a stream over the helper's standard output.
        @raise AudioError: if the program cannot be started.
        """
        process = self._popen(args, subprocess.PIPE, detached=False)
        if process.stdout is None:
            raise AudioError(f"{args[0]} started without an output pipe")
        return PipeStream(process, process.stdout)

    def terminate(self, pid: int, program: str) -> None:
        """Ask a process to stop, but only if it is the expected program.

        Process ids come from the audio graph. Checking the program first
        means a stale or unexpected id can never stop something else, such
        as pipewire-pulse, which owns every virtual mic's node.

        @param pid: the process id.
        @param program: the executable the process must be running.
        """
        if self._program(pid) != program:
            log.warning("Not stopping process %s: it is not %s", pid, program)
            return
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
        child = self._children.pop(pid, None)
        if child is not None:
            reap(child)

    def _reap_exited(self) -> None:
        """Collect helpers that exited on their own.

        A gain stage that crashes stays a zombie until its exit status is
        read. Checking before each start keeps them from piling up.
        """
        for pid, child in list(self._children.items()):
            if child.poll() is not None:
                del self._children[pid]

    def _program(self, pid: int) -> str | None:
        try:
            return (self._proc / str(pid) / "comm").read_text(encoding="utf-8").strip()
        except OSError:
            return None

    @staticmethod
    def _popen(args: Sequence[str], stdout: int, detached: bool) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                list(args),
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                start_new_session=detached,
            )
        except OSError as error:
            raise AudioError(f"{args[0]} could not be started: {error}") from error
