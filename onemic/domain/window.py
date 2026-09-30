from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Corner(Enum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"

    @property
    def is_left(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.BOTTOM_LEFT)

    @property
    def is_top(self) -> bool:
        return self in (Corner.TOP_LEFT, Corner.TOP_RIGHT)


@dataclass(frozen=True)
class WindowState:
    """Where the window lives between runs.

    The screen is stored by connector name (DP-2, HDMI-0) because that is
    stable across reboots, unlike its position in the screen list.
    """

    corner: Corner = Corner.BOTTOM_RIGHT
    screen: str | None = None
    expanded: bool = False
