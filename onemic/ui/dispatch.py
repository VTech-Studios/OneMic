from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot


class MainThreadDispatcher(QObject):
    """Runs callables on the interface thread, from any thread.

    Qt widgets may only be touched from the thread that created them.
    Background results are posted here, and Qt's queued connection carries
    them across to the interface thread's event loop.
    """

    _posted = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._posted.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def post(self, callback: Callable[[], None]) -> None:
        """Queue a callable to run on the interface thread.

        @param callback: the work, which may touch widgets.
        """
        self._posted.emit(callback)

    @Slot(object)
    def _run(self, callback: Callable[[], None]) -> None:
        callback()
