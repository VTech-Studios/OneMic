from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from ..domain.levels import Level


@dataclass(frozen=True)
class Palette:
    """Every colour the window uses, in one place.

    The window is always dark, like a DAW's mixer, because a waveform reads
    best as light on dark and the window has to stay legible at a glance.
    """

    background: str = "#15181c"
    panel: str = "#1e2328"
    border: str = "#2c333b"
    text: str = "#d9e1e8"
    dim: str = "#7d8894"
    ice: str = "#79d4ff"
    hot: str = "#ffc93d"
    clip: str = "#ff4a4a"
    live: str = "#e3342f"
    muted: str = "#c0392b"

    def level_colour(self, level: Level) -> QColor:
        """Pick the colour that tells the user how close a signal is to clipping.

        @param level: the graded peak.
        @return: ice blue when safe, yellow when hot, red when clipping.
        """
        return QColor({Level.SAFE: self.ice, Level.HOT: self.hot, Level.CLIP: self.clip}[level])


def stylesheet(palette: Palette) -> str:
    """Build the Qt stylesheet for the window and its dialogs.

    @param palette: the colours to use.
    @return: a stylesheet that styles widgets by object name.
    """
    return f"""
    QWidget {{ color: {palette.text}; font-size: 9pt; }}
    QDialog, QMenu {{ background: {palette.background}; }}
    QLabel#dim, QLabel#peak {{ color: {palette.dim}; }}
    QLabel#peak {{ font-family: monospace; }}
    QLabel#error {{ color: {palette.hot}; }}
    QPushButton, QToolButton, QComboBox {{
        background: {palette.panel}; border: 1px solid {palette.border};
        border-radius: 4px; padding: 2px 6px;
    }}
    QPushButton:hover, QToolButton:hover, QComboBox:hover {{ border-color: {palette.ice}; }}
    QPushButton#live {{ font-weight: bold; padding: 3px 10px; }}
    QPushButton#live:checked {{ background: {palette.live}; border-color: {palette.live}; color: white; }}
    QToolButton:checked {{ background: {palette.ice}; color: {palette.background}; }}
    QToolButton#mute, QToolButton#remove {{ padding: 0; font-weight: bold; }}
    QToolButton#mute:checked {{ background: {palette.muted}; color: white; border-color: {palette.muted}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QSlider::groove:horizontal {{ height: 3px; background: {palette.border}; border-radius: 1px; }}
    QSlider::sub-page:horizontal {{ background: {palette.ice}; border-radius: 1px; }}
    QSlider::handle:horizontal {{
        width: 10px; margin: -4px 0; border-radius: 5px; background: {palette.text};
    }}
    QListWidget, QTreeWidget, QLineEdit {{
        background: {palette.panel}; border: 1px solid {palette.border}; border-radius: 4px;
    }}
    """
