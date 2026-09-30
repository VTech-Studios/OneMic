from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QObject, QTimer

from ..domain.errors import ProfileError
from ..domain.profile import MicProfile
from ..domain.sources import AudioSource
from ..domain.window import WindowState
from ..ports import WindowStateStore
from ..services.library import ProfileLibrary
from ..services.session import SessionStatus
from .dialogs import CloseChoice, Dialogs
from .main_window import MainWindow
from .meter_pump import MeterPump
from .mic_actions import LibraryMicActions
from .session_client import SessionClient

RECONCILE_MS = 1000
SAVE_DELAY_MS = 400


class AppController(QObject):
    """Connects what the user does in the window to the library and the session.

    Every edit follows the same path: change the library, show the result,
    tell the session, and schedule a save. Saves are delayed slightly, so a
    slider drag writes the file once rather than on every step.
    """

    def __init__(
        self,
        *,
        window: MainWindow,
        library: ProfileLibrary,
        client: SessionClient,
        meters: MeterPump,
        window_store: WindowStateStore,
        dialogs: Dialogs,
        quit_application: Callable[[], None],
    ) -> None:
        super().__init__(window)
        self._window = window
        self._library = library
        self._client = client
        self._meters = meters
        self._window_store = window_store
        self._dialogs = dialogs
        self._quit = quit_application
        self._status = SessionStatus()
        self._requested: str | None = None
        self._reconcile_timer = QTimer(self, interval=RECONCILE_MS)
        self._save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS)
        self._connect()

    @property
    def status(self) -> SessionStatus:
        return self._status

    def start(self) -> None:
        """Show the window where it was left and look for a mic already live."""
        self._show_library()
        self._window.place()
        self._window.show()
        self._client.adopt(self._library.profiles)

    def _connect(self) -> None:
        self._connect_header()
        self._connect_rows()
        self._client.status_changed.connect(self._on_status)
        self._client.failed.connect(self._on_failure)
        self._client.sources_ready.connect(self._on_sources)
        self._window.state_changed.connect(self._on_window_state)
        self._reconcile_timer.timeout.connect(self._client.reconcile)
        self._save_timer.timeout.connect(self._library.save)

    def _connect_header(self) -> None:
        header = self._window.header
        header.live_toggled.connect(self._on_live_toggled)
        header.listen_toggled.connect(self._client.set_listening)
        header.mic_selected.connect(self._on_mic_selected)
        header.add_input_requested.connect(self._client.list_sources)
        header.manage_requested.connect(self._on_manage)
        header.close_requested.connect(self._on_close)

    def _connect_rows(self) -> None:
        window = self._window
        window.input_gain_changed.connect(
            lambda key, gain: self._edit_levels(lambda profile: profile.with_input_gain(key, gain))
        )
        window.input_mute_toggled.connect(
            lambda key, muted: self._edit_levels(lambda profile: profile.with_input_muted(key, muted))
        )
        window.mix_gain_changed.connect(
            lambda gain: self._edit_levels(lambda profile: profile.with_gain(gain))
        )
        window.mix_mute_toggled.connect(
            lambda muted: self._edit_levels(lambda profile: profile.with_muted(muted))
        )
        window.input_remove_requested.connect(
            lambda key: self._edit_inputs(lambda profile: profile.without_input(key))
        )

    def _on_status(self, status: SessionStatus) -> None:
        """Show the session's state, which is always the answer to the latest request.

        Older answers never arrive here, so the mic that was asked to go
        live can be taken from the status itself. A live mic that has since
        been deleted is stopped rather than shown.

        @param status: the session's status.
        """
        if status.live_slug and self._library.find(status.live_slug) is None:
            self._client.stop()
            return
        self._status = status
        self._requested = status.live_slug
        if status.live_slug and status.live_slug != self._library.selected.slug:
            self._library.select(status.live_slug)
            self._show_library()
        self._window.show_status(status)
        self._follow_meters()
        if status.live:
            self._reconcile_timer.start()
        else:
            self._reconcile_timer.stop()

    def _on_failure(self, message: str) -> None:
        """Show what went wrong and put the controls back to the real state.

        A toggle flips as soon as it is clicked. If the work behind it then
        fails, the toggle would claim a state that does not exist, such as
        showing LIVE when no mic was made.

        @param message: what went wrong, in plain words.
        """
        self._window.show_error(message)
        self._window.show_status(self._status)

    def _on_live_toggled(self, live: bool) -> None:
        if live:
            self._go_live(self._library.selected)
        else:
            self._requested = None
            self._client.stop()

    def _on_mic_selected(self, slug: str) -> None:
        profile = self._library.select(slug)
        self._window.show_profile(profile)
        self._save_timer.start()
        if self._requested:
            self._go_live(profile)

    def _go_live(self, profile: MicProfile) -> None:
        self._requested = profile.slug
        self._client.go_live(profile)

    def _protected(self) -> set[str]:
        """Name the mics that must not be renamed or deleted.

        That is the live mic and any mic still on its way to going live,
        because the status reporting it may not have arrived yet.

        @return: the protected slugs.
        """
        return {slug for slug in (self._requested, self._status.live_slug) if slug}

    def _edit_levels(self, change: Callable[[MicProfile], MicProfile]) -> None:
        profile = self._library.update(change(self._library.selected))
        self._client.apply_levels(profile)
        self._save_timer.start()

    def _edit_inputs(self, change: Callable[[MicProfile], MicProfile]) -> None:
        try:
            profile = self._library.update(change(self._library.selected))
        except ProfileError as error:
            self._window.show_error(str(error))
            return
        self._window.show_profile(profile)
        self._client.update(profile)
        self._follow_meters()
        self._save_timer.start()

    def _on_sources(self, sources: Sequence[AudioSource]) -> None:
        used = {settings.source for settings in self._library.selected.inputs}
        chosen = self._dialogs.pick_source(sources, used)
        if chosen is not None:
            self._edit_inputs(lambda profile: profile.with_input(self._library.new_input(chosen)))

    def _on_manage(self) -> None:
        self._dialogs.manage_mics(LibraryMicActions(self._library, self._protected))
        if self._requested:
            self._library.select(self._requested)
        self._show_library()
        self._save_timer.start()

    def _on_window_state(self, state: WindowState) -> None:
        self._window_store.save(state)
        self._follow_meters()

    def _on_close(self) -> None:
        choice = CloseChoice.KEEP_LIVE
        if self._requested or self._status.live:
            choice = self._dialogs.ask_on_close(self._library.selected.name)
        if choice is CloseChoice.CANCEL:
            return
        self._reconcile_timer.stop()
        self._meters.close()
        self._client.shutdown(stop_mic=choice is CloseChoice.STOP)
        self._library.save()
        self._window.allow_close()
        self._window.close()
        self._quit()

    def _follow_meters(self) -> None:
        self._meters.follow(self._status.live_slug, self._window.visible_inputs())

    def _show_library(self) -> None:
        selected = self._library.selected
        self._window.header.show_profiles(self._library.profiles, selected.slug)
        self._window.show_profile(selected)
