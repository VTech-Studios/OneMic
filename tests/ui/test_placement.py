import pytest
from PySide6.QtCore import QPoint, QRect, QSize

from onemic.domain.window import Corner
from onemic.ui.placement import nearest_corner, position_for

AREA = QRect(0, 0, 1920, 1080)
SIZE = QSize(340, 200)


@pytest.mark.parametrize(
    ("x", "y", "corner"),
    [
        (10, 10, Corner.TOP_LEFT),
        (1500, 10, Corner.TOP_RIGHT),
        (10, 800, Corner.BOTTOM_LEFT),
        (1500, 800, Corner.BOTTOM_RIGHT),
    ],
)
def test_a_dropped_window_snaps_to_the_nearest_corner(x: int, y: int, corner: Corner) -> None:
    assert nearest_corner(QRect(QPoint(x, y), SIZE), AREA) is corner


@pytest.mark.parametrize(
    ("corner", "expected"),
    [
        (Corner.TOP_LEFT, QPoint(12, 12)),
        (Corner.TOP_RIGHT, QPoint(1920 - 340 - 12, 12)),
        (Corner.BOTTOM_LEFT, QPoint(12, 1080 - 200 - 12)),
        (Corner.BOTTOM_RIGHT, QPoint(1920 - 340 - 12, 1080 - 200 - 12)),
    ],
)
def test_windows_sit_a_margin_in_from_their_corner(corner: Corner, expected: QPoint) -> None:
    assert position_for(corner, SIZE, AREA) == expected


def test_positions_respect_a_screen_that_is_not_at_the_origin() -> None:
    right_screen = QRect(3840, 0, 3440, 1440)

    assert position_for(Corner.TOP_LEFT, SIZE, right_screen) == QPoint(3852, 12)


def test_a_taller_window_grows_upward_from_a_bottom_corner() -> None:
    short = position_for(Corner.BOTTOM_RIGHT, QSize(340, 200), AREA)
    tall = position_for(Corner.BOTTOM_RIGHT, QSize(340, 500), AREA)

    assert tall.y() == short.y() - 300
