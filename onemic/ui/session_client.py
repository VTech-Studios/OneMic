from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..domain.errors import AudioError
from ..domain.profile import MicProfile
from ..domain.sources import available_sources
from ..ports import AudioGraph
from ..services.session import MicSession
from ..services.worker import LatestJobWorker
from .dispatch import MainThreadDispatcher


class SessionClient(QObject):
    """Runs session work in the background and reports back on the interface thread.

    Reading and rewiring the graph takes tens of milliseconds, long enough
    to stutter the waveforms, so none of it happens on the interface thread.
    Results arrive as signals, which widgets can safely act on.
    """

    status_changed = Signal(object)
    sources_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        session: MicSession,
        graph: AudioGraph,
        worker: LatestJobWorker,
        dispatcher: MainThreadDispatcher,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._graph = graph
        self._worker = worker
        self._dispatcher = dispatcher

    def adopt(self, profiles: Sequence[MicProfile]) -> None:
        """Look for a mic left live by an earlier run.

        @param profiles: every saved mic.
        """
        self._submit("state", lambda: self._session.adopt(profiles))

    def go_live(self, profile: MicProfile) -> None:
        """Make a mic live.

        @param profile: the mic to make live.
        """
        self._submit("state", lambda: self._session.go_live(profile))

    def stop(self) -> None:
        """Take the live mic down."""
        self._submit("state", self._session.stop)

    def update(self, profile: MicProfile) -> None:
        """Apply structural edits, such as an input added or removed.

        @param profile: the edited mic.
        """
        self._submit("update", lambda: self._session.update(profile))

    def apply_levels(self, profile: MicProfile) -> None:
        """Apply volume and mute changes, keeping only the newest while a slider moves.

        @param profile: the edited mic.
        """
        self._submit("levels", lambda: self._session.apply_levels(profile), report=False)

    def set_listening(self, listening: bool) -> None:
        """Start or stop playing the mic through the default output.

        @param listening: True to hear the mic.
        """
        self._submit("listen", lambda: self._session.set_listening(listening))

    def reconcile(self) -> None:
        """Repair the live mic's wiring, skipped if a repair is already queued."""
        if not self._worker.is_pending("reconcile"):
            self._submit("reconcile", self._session.reconcile)

    def list_sources(self) -> None:
        """Read the graph for the add-input picker."""
        self._worker.submit(
            "sources",
            lambda: available_sources(self._graph.snapshot()),
            lambda sources: self._dispatcher.post(lambda: self.sources_ready.emit(sources)),
            self._report_failure,
        )

    def shutdown(self, stop_mic: bool) -> None:
        """Finish background work, then stop the mic if asked, before the application exits.

        Runs on the calling thread after the worker has stopped, so the
        final teardown cannot race a queued job.

        @param stop_mic: True to take the mic down, False to leave it live.
        """
        self._worker.shutdown()
        try:
            if stop_mic:
                self._session.stop()
            else:
                self._session.set_listening(False)
        except AudioError as error:
            self.failed.emit(str(error))

    def _submit(self, key: str, job: Callable[[], Any], report: bool = True) -> None:
        self._worker.submit(key, job, self._emit_status if report else lambda _: None, self._report_failure)

    def _emit_status(self, status: object) -> None:
        self._dispatcher.post(lambda: self.status_changed.emit(status))

    def _report_failure(self, error: Exception) -> None:
        self._dispatcher.post(lambda: self.failed.emit(str(error)))
