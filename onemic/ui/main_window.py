from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QScreen,
)
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ..domain.levels import LevelThresholds
from ..domain.naming import MIX_TAP
from ..domain.profile import MicProfile
from ..domain.window import WindowState
from ..services.metering import EMPTY_READING, MeterReading
from ..services.routing import InputState
from ..services.session import SessionStatus
from .channel_row import ChannelRow
from .header import HeaderBar
from .placement import nearest_corner, position_for
from .theme import Palette

COMPACT_INPUTS = 2
WIDTH = 360
RADIUS = 10
ERROR_SECONDS = 8


class MainWindow(QWidget):
    """The small always-on-top window: header, input rows and the mix row.

    It shows state and reports intent through signals, and holds no
    settings of its own beyond where it sits, so the controller stays the
    only place that decides anything.
    """

    input_gain_changed = Signal(str, float)
    input_mute_toggled = Signal(str, bool)
    input_remove_requested = Signal(str)
    mix_gain_changed = Signal(float)
    mix_mute_toggled = Signal(bool)
    state_changed = Signal(object)

    def __init__(self, palette: Palette, thresholds: LevelThresholds, state: WindowState) -> None:
        super().__init__(None, self._window_flags())
        self._palette = palette
        self._thresholds = thresholds
        self._state = state
        self._live = False
        self._may_close = False
        self._drag_from: QPoint | None = None
        self._rows: dict[str, ChannelRow] = {}
        self.header = HeaderBar()
        self._mix = self._make_mix_row()
        self._inputs = QVBoxLayout()
        self._more = QLabel()
        self._more.setObjectName("dim")
        self._add = QPushButton("Add input…")
        self._error = QLabel(wordWrap=True)
        self._error.setObjectName("error")
        self._error_timer = QTimer(self, singleShot=True, interval=ERROR_SECONDS * 1000)
        self._configure()
        self._build_layout()
        self._connect()

    @staticmethod
    def _window_flags() -> Qt.WindowType:
        return Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint

    def show_profile(self, profile: MicProfile) -> None:
        """Show a mic's inputs and levels, rebuilding rows only when inputs change.

        Rebuilding on every edit would reset each waveform, so rows are kept
        and updated in place while the set of inputs is the same.

        @param profile: the mic to show.
        """
        if list(self._rows) != [settings.id for settings in profile.inputs]:
            self._rebuild_rows(profile)
        for settings in profile.inputs:
            self._rows[settings.id].set_values(settings.label, settings.gain, settings.muted)
        self._mix.set_values(f"Mix → {profile.name}", profile.gain, profile.muted)
        self._update_visibility()

    def show_status(self, status: SessionStatus) -> None:
        """Show whether the mic is live and how each input is doing.

        @param status: the session's latest status.
        """
        self._live = status.live
        self.header.show_status(status.live, status.listening, status.listen_blocked)
        for key, row in self._rows.items():
            row.set_state(status.inputs.get(key, InputState.OFF) if status.live else InputState.OFF)
        self._mix.set_state(InputState.LIVE if status.live else InputState.OFF)
        if not status.live:
            self.show_levels({})
        self.update()

    def show_levels(self, readings: Mapping[str, MeterReading]) -> None:
        """Draw the latest waveforms and peaks on the rows that are visible.

        @param readings: meter readings keyed by input id or the mix key.
        """
        for key, row in [*self._rows.items(), (MIX_TAP, self._mix)]:
            if row.isVisible():
                row.set_reading(readings.get(key, EMPTY_READING))

    def show_error(self, message: str) -> None:
        """Show a problem briefly without interrupting with a dialog.

        @param message: what went wrong, in plain words.
        """
        self._error.setText(message)
        self._error.show()
        self._error_timer.start()
        self._settle()

    def set_expanded(self, expanded: bool) -> None:
        """Switch between two inputs and every input.

        @param expanded: True to show every input and the add button.
        """
        self._state = replace(self._state, expanded=expanded)
        self.header.set_expanded(expanded)
        self._update_visibility()
        self.state_changed.emit(self._state)

    def visible_inputs(self) -> list[str]:
        """List the inputs whose rows are on screen, so only those are metered.

        @return: input ids in display order.
        """
        return [key for key, row in self._rows.items() if not row.isHidden()]

    def place(self) -> None:
        """Move the window to its corner on its saved screen, at its current size."""
        self.adjustSize()
        area = self._screen().availableGeometry()
        self.move(position_for(self._state.corner, self.size(), area))

    def allow_close(self) -> None:
        """Let the next close go ahead, once the controller has dealt with a live mic."""
        self._may_close = True

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._may_close:
            event.accept()
            return
        event.ignore()
        self.header.close_requested.emit()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border = self._palette.live if self._live else self._palette.border
        painter.setPen(QPen(QColor(border), 2 if self._live else 1))
        painter.setBrush(QColor(self._palette.panel))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), RADIUS, RADIUS)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is not None:
            self.move(event.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_from is None:
            return
        self._drag_from = None
        screen = self.screen()
        corner = nearest_corner(self.frameGeometry(), screen.availableGeometry())
        self._state = replace(self._state, corner=corner, screen=screen.name())
        self.place()
        self.state_changed.emit(self._state)

    def _screen(self) -> QScreen:
        screens = {screen.name(): screen for screen in QGuiApplication.screens()}
        return screens.get(self._state.screen or "") or QGuiApplication.primaryScreen()

    def _make_mix_row(self) -> ChannelRow:
        row = ChannelRow(MIX_TAP, self._palette, self._thresholds)
        row.set_removable(False)
        row.gain_changed.connect(lambda _, gain: self.mix_gain_changed.emit(gain))
        row.mute_toggled.connect(lambda _, muted: self.mix_mute_toggled.emit(muted))
        return row

    def _rebuild_rows(self, profile: MicProfile) -> None:
        for row in self._rows.values():
            row.deleteLater()
        self._rows = {}
        for settings in profile.inputs:
            row = ChannelRow(settings.id, self._palette, self._thresholds)
            row.gain_changed.connect(self.input_gain_changed.emit)
            row.mute_toggled.connect(self.input_mute_toggled.emit)
            row.remove_requested.connect(self.input_remove_requested.emit)
            self._inputs.addWidget(row)
            self._rows[settings.id] = row

    def _update_visibility(self) -> None:
        expanded = self._state.expanded
        for index, row in enumerate(self._rows.values()):
            row.setVisible(expanded or index < COMPACT_INPUTS)
            row.set_removable(expanded)
        hidden = max(len(self._rows) - COMPACT_INPUTS, 0)
        self._more.setText(f"+{hidden} more, expand to see {'it' if hidden == 1 else 'them'}")
        self._more.setVisible(hidden > 0 and not expanded)
        self._add.setVisible(expanded or not self._rows)
        self._settle()

    def _settle(self) -> None:
        """Re-place the window once Qt has finished resizing it.

        Showing or hiding rows changes the height only after the layout
        runs, so placing immediately would use the old size and the window
        would drift away from its corner.
        """
        QTimer.singleShot(0, self.place)

    def _configure(self) -> None:
        self.setWindowTitle("OneMic")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(WIDTH)
        self._error.hide()
        self._inputs.setSpacing(8)

    def _build_layout(self) -> None:
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 10)
        column.setSpacing(8)
        column.addWidget(self.header)
        column.addLayout(self._inputs)
        column.addWidget(self._more)
        column.addWidget(self._add)
        column.addWidget(self._mix)
        column.addWidget(self._error)

    def _connect(self) -> None:
        self.header.expand_toggled.connect(self.set_expanded)
        self._add.clicked.connect(self.header.add_input_requested.emit)
        self._error_timer.timeout.connect(self._error.hide)
        self._error_timer.timeout.connect(self._settle)
