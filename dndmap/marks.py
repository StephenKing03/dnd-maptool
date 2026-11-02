"""Geometry of table marks (texts, shapes, image objects): size, hit tests, handles, snapping."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFontMetricsF

from dndmap import style
from dndmap.model import TableMark

LINE_KINDS = ("line", "arrow")
MIN_SIZE = 0.25


def text_extent(text: str, text_size: float) -> tuple[float, float]:
    """Width and height in squares of a text plate whose text is text_size squares tall."""
    fm = QFontMetricsF(style.note_font(100))
    h = fm.height()
    pad = h * 0.35
    return ((fm.horizontalAdvance(text or " ") + 2 * pad) / 100 * text_size,
            (h + pad * 0.8) / 100 * text_size)


def size(k: TableMark) -> tuple[float, float]:
    if k.kind == "text":
        return text_extent(k.text, k.text_size)
    if k.kind in LINE_KINDS:
        return math.hypot(k.x2 - k.x, k.y2 - k.y), 0.0
    return k.w, k.h


def center(k: TableMark) -> QPointF:
    if k.kind in LINE_KINDS:
        return QPointF((k.x + k.x2) / 2, (k.y + k.y2) / 2)
    return QPointF(k.x, k.y)


def _rot(p: QPointF, deg: float) -> QPointF:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return QPointF(p.x() * c - p.y() * s, p.x() * s + p.y() * c)


def to_local(k: TableMark, p: QPointF) -> QPointF:
    return _rot(p - center(k), -k.rotation)


def to_map(k: TableMark, lp: QPointF) -> QPointF:
    return center(k) + _rot(lp, k.rotation)


def _seg_dist(p, a, b) -> float:
    ab = b - a
    n = ab.x() ** 2 + ab.y() ** 2
    if n < 1e-9:
        return math.hypot((p - a).x(), (p - a).y())
    t = max(0.0, min(1.0, ((p - a).x() * ab.x() + (p - a).y() * ab.y()) / n))
    d = p - (a + ab * t)
    return math.hypot(d.x(), d.y())


def contains(k: TableMark, p: QPointF, tol: float) -> bool:
    if k.kind in LINE_KINDS:
        return _seg_dist(p, QPointF(k.x, k.y), QPointF(k.x2, k.y2)) <= tol
    w, h = size(k)
    lp = to_local(k, p)
    hw, hh = w / 2 + tol, h / 2 + tol
    if k.kind == "circle":
        return (lp.x() / hw) ** 2 + (lp.y() / hh) ** 2 <= 1
    if k.kind == "triangle":
        if not (-hh <= lp.y() <= hh):
            return False
        t = (lp.y() + hh) / (2 * hh)          # 0 at the apex, 1 at the base
        return abs(lp.x()) <= hw * t + tol
    return abs(lp.x()) <= hw and abs(lp.y()) <= hh


def corners(k: TableMark) -> list[QPointF]:
    if k.kind in LINE_KINDS:
        return [QPointF(k.x, k.y), QPointF(k.x2, k.y2)]
    w, h = size(k)
    return [to_map(k, QPointF(sx * w / 2, sy * h / 2)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def bounds(k: TableMark) -> QRectF:
    pts = corners(k)
    xs, ys = [p.x() for p in pts], [p.y() for p in pts]
    return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))


HANDLE_POS = {"nw": (-1, -1), "n": (0, -1), "ne": (1, -1), "e": (1, 0),
              "se": (1, 1), "s": (0, 1), "sw": (-1, 1), "w": (-1, 0)}


def handles(k: TableMark, rot_offset: float) -> dict[str, QPointF]:
    """Handle positions in map squares. rot_offset = distance of the rotate handle above the top edge."""
    if k.kind in LINE_KINDS:
        return {"p1": QPointF(k.x, k.y), "p2": QPointF(k.x2, k.y2)}
    w, h = size(k)
    names = ("nw", "ne", "se", "sw") if k.kind == "text" else tuple(HANDLE_POS)
    out = {n: to_map(k, QPointF(HANDLE_POS[n][0] * w / 2, HANDLE_POS[n][1] * h / 2)) for n in names}
    out["rot"] = to_map(k, QPointF(0, -h / 2 - rot_offset))
    return out


def _snap_half(v: float) -> float:
    return max(MIN_SIZE, round(v * 2) / 2)


def apply_handle(k: TableMark, orig: TableMark, handle: str, p: QPointF, snap: bool):
    """Resize or rotate k (a working copy of orig) by dragging `handle` to map point p."""
    if handle == "rot":
        c = center(orig)
        ang = math.degrees(math.atan2(p.y() - c.y(), p.x() - c.x())) + 90
        if snap:
            ang = round(ang / 15) * 15
        k.rotation = (ang + 180) % 360 - 180
        return
    if handle in ("p1", "p2"):
        q = QPointF(math.floor(p.x()) + 0.5, math.floor(p.y()) + 0.5) if snap else p
        if handle == "p1":
            k.x, k.y = q.x(), q.y()
        else:
            k.x2, k.y2 = q.x(), q.y()
        return
    lp = to_local(orig, p)
    w0, h0 = size(orig)
    if k.kind == "text":
        hx, hy = HANDLE_POS[handle]
        ref = math.hypot(hx * w0 / 2, hy * h0 / 2) or 1.0
        factor = math.hypot(lp.x(), lp.y()) / ref
        size_ = orig.text_size * factor
        k.text_size = max(0.15, min(6.0, round(size_ * 20) / 20 if snap else size_))
        return
    left, right, top, bottom = -w0 / 2, w0 / 2, -h0 / 2, h0 / 2
    if "e" in handle:
        right = lp.x()
    if "w" in handle:
        left = lp.x()
    if "n" in handle:
        top = lp.y()
    if "s" in handle:
        bottom = lp.y()
    w, h = right - left, bottom - top
    if snap:
        w, h = _snap_half(abs(w)), _snap_half(abs(h))
        if "w" in handle:
            left = right - w
        else:
            right = left + w
        if "n" in handle:
            top = bottom - h
        else:
            bottom = top + h
    else:
        w, h = max(MIN_SIZE, abs(w)), max(MIN_SIZE, abs(h))
    k.w, k.h = w, h
    c = to_map(orig, QPointF((left + right) / 2, (top + bottom) / 2))
    k.x, k.y = c.x(), c.y()


def move(k: TableMark, dx: float, dy: float):
    k.x += dx
    k.y += dy
    if k.kind in LINE_KINDS:
        k.x2 += dx
        k.y2 += dy


def snap_delta(k: TableMark, dx: float, dy: float) -> tuple[float, float]:
    """Adjust a move so the mark lands on the grid: whole-square sizes on grid lines,
    everything else centred in a square; lines start on a square centre."""
    if k.kind in LINE_KINDS:
        nx, ny = math.floor(k.x + dx) + 0.5, math.floor(k.y + dy) + 0.5
        return nx - k.x, ny - k.y
    b = bounds(k)
    out = []
    for c, length, d, lo in ((k.x, b.width(), dx, b.left()), (k.y, b.height(), dy, b.top())):
        if k.kind != "text" and abs(length - round(length)) < 0.02 and round(length) >= 1:
            out.append(round(lo + d) - lo)
        else:
            out.append(math.floor(c + d) + 0.5 - c)
    return out[0], out[1]
