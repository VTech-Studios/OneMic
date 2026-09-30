from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget

from ..domain.levels import SILENCE_DB, LevelThresholds, amplitude_to_db
from ..domain.profile import MAX_GAIN
from ..services.metering import EMPTY_READING, MeterReading
from ..services.routing import InputState
from .theme import Palette
from .waveform import WaveformView
from .widgets import tool_button

STATE_HINTS = {
    InputState.OFF: "Not live. The waveform shows the source itself, before this input's volume.",
    InputState.STARTING: "Starting",
    InputState.WAITING: "Waiting for this source to appear",
    InputState.LIVE: "Live",
}


def format_peak(peak: float) -> str:
    """Format a held peak the way a DAW's meter reads.

    @param peak: absolute peak amplitude, where 1.0 is full scale.
    @return: dBFS to one decimal place, or -inf for silence.
    """
    db = amplitude_to_db(peak)
    return "-inf" if db <= SILENCE_DB else f"{db:.1f}"


class ChannelRow(QWidget):
    """One signal's controls and waveform: an input, or the mix the mic sends.

    Rows only report what the user did. They never change settings
    themselves, so the saved mic stays the single source of truth.
    """

    gain_changed = Signal(str, float)
    mute_toggled = Signal(str, bool)
    remove_requested = Signal(str)

    def __init__(
        self, key: str, palette: Palette, thresholds: LevelThresholds, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._palette = palette
        self._thresholds = thresholds
        self._title = QLabel()
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._peak_colour = ""
        self._mute = self._small_button(tool_button("M", "Mute", checkable=True, name="mute"))
        self._remove = self._small_button(tool_button("✕", "Remove this input", name="remove"))
        self._slider = self._gain_slider()
        self._peak = QLabel(format_peak(0.0))
        self._peak.setObjectName("peak")
        self._peak.setFixedWidth(40)
        self._peak.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.waveform = WaveformView(palette, thresholds)
        self._build_layout()
        self._connect()

    def set_values(self, label: str, gain: float, muted: bool) -> None:
        """Show saved settings without echoing them back as user changes.

        @param label: the name to show.
        @param gain: the gain, where 1.0 is unity.
        @param muted: the mute state.
        """
        self._title.setText(label)
        self._title.setToolTip(label)
        for widget in (self._slider, self._mute):
            widget.blockSignals(True)
        self._slider.setValue(round(gain * 100))
        self._slider.setToolTip(f"{round(gain * 100)}%")
        self._mute.setChecked(muted)
        for widget in (self._slider, self._mute):
            widget.blockSignals(False)

    def set_state(self, state: InputState) -> None:
        """Dim the name while the signal is not reaching the mic.

        @param state: how far the input has got towards being heard.
        """
        colour = self._palette.text if state is InputState.LIVE else self._palette.dim
        self._title.setStyleSheet(f"color: {colour};")
        self.setToolTip(STATE_HINTS[state])

    def set_reading(self, reading: MeterReading) -> None:
        """Show the latest waveform and held peak.

        @param reading: the meter's current state; EMPTY_READING when not metering.
        """
        self.waveform.set_columns(reading.columns)
        self._peak.setText(format_peak(reading.held_peak))
        self._colour_peak(reading.held_peak)

    def set_removable(self, removable: bool) -> None:
        """Show the remove button only where there is room for it.

        @param removable: True in the expanded view.
        """
        self._remove.setVisible(removable)

    def clear_reading(self) -> None:
        """Blank the waveform once the signal is no longer metered."""
        self.set_reading(EMPTY_READING)

    def _colour_peak(self, peak: float) -> None:
        """Colour the peak readout by level, restyling only when the colour changes.

        Applying a stylesheet re-polishes the widget, which is too costly to
        repeat thirty times a second for every row.

        @param peak: the held peak amplitude.
        """
        level_colour = self._palette.level_colour(self._thresholds.classify(peak)).name()
        colour = level_colour if peak > 0 else self._palette.dim
        if colour != self._peak_colour:
            self._peak_colour = colour
            self._peak.setStyleSheet(f"color: {colour};")

    @staticmethod
    def _small_button(button: QToolButton) -> QToolButton:
        button.setFixedSize(20, 18)
        return button

    def _gain_slider(self) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, round(MAX_GAIN * 100))
        slider.setFixedWidth(84)
        return slider

    def _build_layout(self) -> None:
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(self._mute)
        controls.addWidget(self._title, 1)
        controls.addWidget(self._slider)
        controls.addWidget(self._peak)
        controls.addWidget(self._remove)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        column.addLayout(controls)
        column.addWidget(self.waveform)

    def _connect(self) -> None:
        self._slider.valueChanged.connect(self._on_slider)
        self._mute.toggled.connect(lambda muted: self.mute_toggled.emit(self.key, muted))
        self._remove.clicked.connect(lambda: self.remove_requested.emit(self.key))

    def _on_slider(self, value: int) -> None:
        self._slider.setToolTip(f"{value}%")
        self.gain_changed.emit(self.key, value / 100)
