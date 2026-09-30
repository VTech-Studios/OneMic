from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QToolButton


def tool_button(text: str, tip: str, checkable: bool = False, name: str = "") -> QToolButton:
    """Make a small button, optionally named so the stylesheet can target it.

    @param text: the button's label.
    @param tip: the tooltip.
    @param checkable: True for a toggle.
    @param name: the object name used by the stylesheet, if any.
    @return: the button.
    """
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tip)
    button.setCheckable(checkable)
    button.setObjectName(name)
    return button


def set_icon(button: QToolButton, icon: str, fallback: str) -> None:
    """Show a desktop theme icon, or text where the theme has no such icon.

    Theme icons match the rest of the desktop, and the text fallback means
    the button is never blank.

    @param button: the button to change.
    @param icon: the freedesktop icon name.
    @param fallback: text shown if the theme lacks the icon.
    """
    themed = QIcon.fromTheme(icon)
    if themed.isNull():
        button.setIcon(QIcon())
        button.setText(fallback)
    else:
        button.setText("")
        button.setIcon(themed)


def icon_button(icon: str, fallback: str, tip: str, checkable: bool = False) -> QToolButton:
    """Make a small borderless header button with a desktop theme icon.

    @param icon: the freedesktop icon name.
    @param fallback: text shown if the theme lacks the icon.
    @param tip: the tooltip.
    @param checkable: True for a toggle.
    @return: the button.
    """
    button = tool_button(fallback, tip, checkable)
    set_icon(button, icon, fallback)
    button.setAutoRaise(True)
    return button
