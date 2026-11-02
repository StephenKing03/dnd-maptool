"""Grid rules: distances, affected squares of templates, tile neighbours and coverage."""
from __future__ import annotations

import math

from dndmap.model import GameMap, Template, Tile

FT_PER_SQUARE = 5


def grid_distance(ax, ay, bx, by, rule="5e") -> int:
    """Distance in squares between two square positions.

    rule "5e": every diagonal step costs one square.
    rule "5-10-5": every second diagonal step costs two squares.
    """
    dx = abs(math.floor(bx) - math.floor(ax))
    dy = abs(math.floor(by) - math.floor(ay))
    if rule == "5-10-5":
        return max(dx, dy) + min(dx, dy) // 2
    return max(dx, dy)


def _unit(t: Template):
    vx, vy = t.dx - t.x, t.dy - t.y
    n = math.hypot(vx, vy)
    if n < 1e-6:
        return 1.0, 0.0
    return vx / n, vy / n


def template_contains(t: Template, px, py) -> bool:
    """Does the template cover point (px, py)? Used with square centers (MEA-6)."""
    L = t.size_ft / FT_PER_SQUARE
    eps = 1e-6
    if t.shape in ("sphere", "range"):
        return math.hypot(px - t.x, py - t.y) <= L + eps
    if t.shape == "cube":
        sx = 1 if t.dx >= t.x else -1
        sy = 1 if t.dy >= t.y else -1
        u, v = (px - t.x) * sx, (py - t.y) * sy
        return -eps <= u <= L + eps and -eps <= v <= L + eps
    ux, uy = _unit(t)
    vx, vy = px - t.x, py - t.y
    along = vx * ux + vy * uy
    perp = abs(vx * uy - vy * ux)
    if t.shape == "cone":      # width at a distance equals that distance
        return eps < along <= L + eps and perp <= along / 2 + eps
    if t.shape == "line":      # 5 ft wide
        return -eps <= along <= L + eps and perp <= 0.5 + eps
    return False


def template_squares(t: Template) -> list[tuple[int, int]]:
    if t.shape == "range":
        return []
    L = t.size_ft / FT_PER_SQUARE
    r = int(math.ceil(L)) + 2
    cx, cy = int(math.floor(t.x)), int(math.floor(t.y))
    return [(x, y)
            for x in range(cx - r, cx + r + 1)
            for y in range(cy - r, cy + r + 1)
            if template_contains(t, x + 0.5, y + 0.5)]


DIRECTIONS = ("up", "down", "left", "right")


def neighbour(tiles: list[Tile], tile: Tile, direction: str) -> Tile | None:
    """The tile next to `tile` in a direction: a DM override, else the nearest overlapping one."""
    override = tile.neighbours.get(direction)
    if override:
        return next((t for t in tiles if t.id == override), None)
    best, best_key = None, None
    for t in tiles:
        if t.id == tile.id:
            continue
        if direction in ("left", "right"):
            overlap = min(t.y + t.h, tile.y + tile.h) - max(t.y, tile.y)
            dist = (t.x - tile.x) if direction == "right" else (tile.x - t.x)
        else:
            overlap = min(t.x + t.w, tile.x + tile.w) - max(t.x, tile.x)
            dist = (t.y - tile.y) if direction == "down" else (tile.y - t.y)
        if overlap <= 0 or dist <= 0:
            continue
        key = (dist, -overlap)
        if best_key is None or key < best_key:
            best, best_key = t, key
    return best


def coverage_warnings(m: GameMap) -> list[str]:
    """Gaps between neighbouring tiles and map squares no tile covers (TIL-7)."""
    warnings = []
    if not m.tiles:
        return warnings
    for t in m.tiles:
        for d in ("right", "down"):
            n = neighbour(m.tiles, t, d)
            if n is None:
                continue
            gap = (n.x - (t.x + t.w)) if d == "right" else (n.y - (t.y + t.h))
            if gap > 0:
                warnings.append(f"Gap of {gap} sq between {t.name} and {n.name}")
    b = m.bounds()
    if not b.isNull():
        uncovered = 0
        for x in range(math.floor(b.left()), math.ceil(b.right())):
            for y in range(math.floor(b.top()), math.ceil(b.bottom())):
                if not any(t.contains(x + 0.5, y + 0.5) for t in m.tiles):
                    uncovered += 1
        if uncovered:
            warnings.append(f"{uncovered} map squares are not on any tile")
    return warnings
