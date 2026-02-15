from __future__ import annotations

import tkinter as tk
from pathlib import Path

from .theme import Theme


def _find_project_root() -> Path:
    start = Path(__file__).resolve()
    for candidate in [start.parent, *start.parents]:
        if (candidate / "app.py").exists():
            return candidate
    return start.parents[1]


def get_asset_path(rel_path: str) -> Path:
    project_root = _find_project_root()
    return project_root / rel_path


def make_statforge_icon(size: int = 32) -> tk.PhotoImage:
    image = tk.PhotoImage(width=size, height=size)
    scale = max(1, size // 32)

    steel = "#D8DEE5"
    white = "#FFFFFF"

    def fill_rect(x1: int, y1: int, x2: int, y2: int, color: str) -> None:
        image.put(color, to=(x1, y1, x2, y2))

    def set_px(x: int, y: int, color: str) -> None:
        if 0 <= x < size and 0 <= y < size:
            image.put(color, (x, y))

    def draw_line(x1: int, y1: int, x2: int, y2: int, color: str, width: int = 1) -> None:
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for i in range(steps + 1):
            x = int(x1 + (x2 - x1) * (i / steps))
            y = int(y1 + (y2 - y1) * (i / steps))
            for wx in range(-(width // 2), width // 2 + 1):
                for wy in range(-(width // 2), width // 2 + 1):
                    set_px(x + wx, y + wy, color)

    # Hammer head
    fill_rect(7 * scale, 6 * scale, 18 * scale, 10 * scale, steel)
    fill_rect(18 * scale, 7 * scale, 22 * scale, 9 * scale, white)

    # Hammer handle
    draw_line(15 * scale, 10 * scale, 24 * scale, 24 * scale, white, width=max(1, 2 * scale))

    # Electric arc (single line)
    arc_points = [
        (5 * scale, 22 * scale),
        (10 * scale, 17 * scale),
        (15 * scale, 20 * scale),
        (21 * scale, 14 * scale),
        (27 * scale, 17 * scale),
    ]
    for idx in range(len(arc_points) - 1):
        x1, y1 = arc_points[idx]
        x2, y2 = arc_points[idx + 1]
        draw_line(x1, y1, x2, y2, Theme.ACCENT, width=max(1, scale))

    return image


def draw_statforge_mark(parent: tk.Widget, size: int = 28) -> tk.Canvas:
    canvas = tk.Canvas(
        parent,
        width=size,
        height=size,
        bg=Theme.NAVY,
        highlightthickness=0,
        bd=0,
    )
    scale = max(1, size / 28)

    steel = "#D8DEE5"
    white = "#FFFFFF"

    # Hammer head and peen
    canvas.create_rectangle(
        int(5 * scale),
        int(6 * scale),
        int(16 * scale),
        int(10 * scale),
        fill=steel,
        outline="",
    )
    canvas.create_rectangle(
        int(16 * scale),
        int(7 * scale),
        int(20 * scale),
        int(9 * scale),
        fill=white,
        outline="",
    )

    # Hammer handle
    canvas.create_line(
        int(14 * scale),
        int(10 * scale),
        int(22 * scale),
        int(23 * scale),
        fill=white,
        width=max(1, int(2 * scale)),
    )

    # Single electric arc polyline
    points = [
        int(4 * scale),
        int(20 * scale),
        int(9 * scale),
        int(16 * scale),
        int(13 * scale),
        int(19 * scale),
        int(18 * scale),
        int(13 * scale),
        int(24 * scale),
        int(16 * scale),
    ]
    canvas.create_line(
        *points,
        fill=Theme.ACCENT,
        width=max(1, int(2 * scale)),
        smooth=False,
    )
    return canvas
