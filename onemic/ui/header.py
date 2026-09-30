from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QMenu, QPushButton, QSizePolicy, QToolButton, QWidget

from ..domain.profile import MicProfile
from .widgets import icon_button, set_icon

LIVE_TEXT = "● LIVE"
OFF_TEXT = "GO LIVE"
LISTEN_TIP = "Listen: hear exactly what the mic is sending, through your default output"
LISTEN_OFF_TIP = "Go live first. Listen plays what the mic is sending, so it needs a live mic"
LISTEN_BLOCKED_TIP = "Listening is off because the default output is one of this mic's inputs"


class HeaderBar(QWidget):
    """The live switch, mic selector and window controls.

    The live switch doubles as the live indicator, so the control that
    changes the state is also the one that shows it.
    """

    live_toggled = Signal(bool)
    listen_toggled = Signal(bool)
    mic_selected = Signal(str)
    expand_toggled = Signal(bool)
    add_input_requested = Signal()
    manage_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._live = QPushButton(OFF_TEXT)
        self._live.setObjectName("live")
        self._live.setCheckable(True)
        self._mics = QComboBox()
        self._mics.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._listen = icon_button("audio-headphones", "Listen", LISTEN_TIP, checkable=True)
        self._expand = icon_button("go-down", "▾", "Show every input", checkable=True)
        self._menu = self._menu_button()
        self._close = icon_button("window-close", "✕", "Close")
        self._build_layout()
        self._connect()

    def show_profiles(self, profiles: Sequence[MicProfile], selected: str) -> None:
        """List the saved mics, without reporting the refresh as a selection.

        @param profiles: every mic.
        @param selected: the slug of the mic being shown.
        """
        self._mics.blockSignals(True)
        self._mics.clear()
        for profile in profiles:
            self._mics.addItem(profile.name, profile.slug)
        self._mics.setCurrentIndex(max(self._mics.findData(selected), 0))
        self._mics.blockSignals(False)

    def show_status(self, live: bool, listening: bool, listen_blocked: bool) -> None:
        """Reflect the session's real state, which may differ from what was clicked.

        @param live: True while the shown mic is live.
        @param listening: True while the mic plays through the default output.
        @param listen_blocked: True if listening would feed back.
        """
        for button, checked in ((self._live, live), (self._listen, listening)):
            button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(False)
        self._live.setText(LIVE_TEXT if live else OFF_TEXT)
        self._live.setToolTip("Stop the mic" if live else "Make this mic available to call apps")
        self._listen.setEnabled(live and not listen_blocked)
        self._listen.setToolTip(self._listen_tip(live, listen_blocked))

    @staticmethod
    def _listen_tip(live: bool, listen_blocked: bool) -> str:
        if not live:
            return LISTEN_OFF_TIP
        return LISTEN_BLOCKED_TIP if listen_blocked else LISTEN_TIP

    def set_expanded(self, expanded: bool) -> None:
        """Update the expand button to match the window.

        @param expanded: True while every input is shown.
        """
        self._expand.blockSignals(True)
        self._expand.setChecked(expanded)
        self._expand.blockSignals(False)
        self._expand.setToolTip("Show fewer inputs" if expanded else "Show every input")
        set_icon(self._expand, "go-up" if expanded else "go-down", "▴" if expanded else "▾")

    def _menu_button(self) -> QToolButton:
        button = icon_button("application-menu", "⋮", "More")
        menu = QMenu(button)
        menu.addAction("Add input…", self.add_input_requested.emit)
        menu.addAction("Manage mics…", self.manage_requested.emit)
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        return button

    def _build_layout(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self._live)
        row.addWidget(self._mics, 1)
        for button in (self._listen, self._expand, self._menu, self._close):
            row.addWidget(button)

    def _connect(self) -> None:
        self._live.toggled.connect(self.live_toggled.emit)
        self._listen.toggled.connect(self.listen_toggled.emit)
        self._expand.toggled.connect(self.expand_toggled.emit)
        self._close.clicked.connect(self.close_requested.emit)
        self._mics.currentIndexChanged.connect(
            lambda index: self.mic_selected.emit(self._mics.itemData(index))
        )
