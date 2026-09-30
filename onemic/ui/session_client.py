from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, Signal

from ..domain.errors import AudioError
from ..domain.profile import MicProfile
from ..domain.sources import available_sources
from ..ports import AudioGraph
from ..services.session import MicSession, SessionStatus
from ..services.worker import JobQueue
from .dispatch import MainThreadDispatcher


class SessionClient(QObject):
    """Runs session work in the background and reports back on the interface thread.

    Reading and rewiring the graph takes tens of milliseconds, long enough
    to stutter the waveforms, so none of it happens on the interface thread.

    Every request the user makes starts a new generation. A routine repair
    that was already running when the user clicked reports the world as it
    was before the click, so its result is dropped rather than allowed to
    flip the controls back.
    """

    status_changed = Signal(object)
    sources_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        session: MicSession,
        graph: AudioGraph,
        worker: JobQueue,
        dispatcher: MainThreadDispatcher,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._graph = graph
        self._worker = worker
        self._dispatcher = dispatcher
        self._generation = 0

    def adopt(self, profiles: Sequence[MicProfile]) -> None:
        """Look for a mic left live by an earlier run.

        @param profiles: every saved mic.
        """
        self._request("state", lambda: self._session.adopt(profiles))

    def go_live(self, profile: MicProfile) -> None:
        """Make a mic live.

        @param profile: the mic to make live.
        """
        self._request("state", lambda: self._session.go_live(profile))

    def stop(self) -> None:
        """Take the live mic down."""
        self._request("state", self._session.stop)

    def update(self, profile: MicProfile) -> None:
        """Apply structural edits, such as an input added or removed.

        @param profile: the edited mic.
        """
        self._request("update", lambda: self._session.update(profile))

    def set_listening(self, listening: bool) -> None:
        """Start or stop playing the mic through the default output.

        @param listening: True to hear the mic.
        """
        self._request("listen", lambda: self._session.set_listening(listening))

    def apply_levels(self, profile: MicProfile) -> None:
        """Apply volume and mute changes, keeping only the newest while a slider moves.

        @param profile: the edited mic.
        """
        self._worker.submit("levels", lambda: self._session.apply_levels(profile), lambda _: None, self._fail)

    def reconcile(self) -> None:
        """Repair the live mic's wiring, skipped if a repair is already queued."""
        if not self._worker.is_pending("reconcile"):
            self._submit("reconcile", self._session.reconcile, self._generation)

    def list_sources(self) -> None:
        """Read the graph for the add-input picker."""
        self._worker.submit(
            "sources",
            lambda: available_sources(self._graph.snapshot()),
            lambda sources: self._dispatcher.post(lambda: self.sources_ready.emit(sources)),
            self._fail,
        )

    def shutdown(self, stop_mic: bool) -> None:
        """Finish queued work, then stop the mic if asked, before the application exits.

        Runs on the calling thread once the worker has drained, so the final
        teardown cannot race a job still in the queue.

        @param stop_mic: True to take the mic down, False to leave it live without listening.
        """
        self._worker.shutdown()
        try:
            if stop_mic:
                self._session.stop()
            else:
                self._session.set_listening(False)
        except AudioError as error:
            self.failed.emit(str(error))

    def _request(self, key: str, job: Callable[[], SessionStatus]) -> None:
        self._generation += 1
        self._submit(key, job, self._generation)

    def _submit(self, key: str, job: Callable[[], SessionStatus], generation: int) -> None:
        self._worker.submit(
            key,
            job,
            lambda status: self._post_status(generation, status),
            lambda error: self._fail_with_status(generation, error),
        )

    def _post_status(self, generation: int, status: SessionStatus) -> None:
        self._dispatcher.post(lambda: self._emit_if_current(generation, status))

    def _fail_with_status(self, generation: int, error: Exception) -> None:
        """Report a failure along with what is really true now.

        The session undoes a failed request, so its status after the failure
        is what the controls should show, not whatever was clicked.

        @param generation: the generation the failed job belonged to.
        @param error: what went wrong.
        """
        self._post_status(generation, self._session.status())
        self._fail(error)

    def _fail(self, error: Exception) -> None:
        self._dispatcher.post(lambda: self.failed.emit(str(error)))

    def _emit_if_current(self, generation: int, status: SessionStatus) -> None:
        if generation == self._generation:
            self.status_changed.emit(status)
