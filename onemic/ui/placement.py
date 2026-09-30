from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

from ..domain.window import Corner

MARGIN = 12


def nearest_corner(window: QRect, area: QRect) -> Corner:
    """Choose the corner a dropped window should snap to.

    @param window: where the window was dropped.
    @param area: the usable part of the screen it was dropped on.
    @return: the corner on the same side as the window's centre.
    """
    centre = window.center()
    left = centre.x() < area.center().x()
    top = centre.y() < area.center().y()
    if top:
        return Corner.TOP_LEFT if left else Corner.TOP_RIGHT
    return Corner.BOTTOM_LEFT if left else Corner.BOTTOM_RIGHT


def position_for(corner: Corner, size: QSize, area: QRect, margin: int = MARGIN) -> QPoint:
    """Place a window of a given size in a corner of the screen.

    Positions are measured from the corner, so a window that grows when
    expanded grows away from the corner and never off the screen.

    @param corner: the corner to sit in.
    @param size: the window's current size.
    @param area: the usable part of the screen, excluding panels.
    @param margin: the gap to leave at the screen edges.
    @return: the window's top-left position.
    """
    x = area.left() + margin if corner.is_left else area.right() - size.width() - margin + 1
    y = area.top() + margin if corner.is_top else area.bottom() - size.height() - margin + 1
    return QPoint(x, y)
