"""Drawing of maps, fog, measurements and marks. Shared by the DM view, table and preview."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFontMetricsF, QImage, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF, QTransform)

from dndmap import marks, style
from dndmap.geometry import FT_PER_SQUARE, grid_distance, template_squares
from dndmap.model import Fog, GameMap, Marker, PlayerState, Remark, TableMark, Template, Tile

_pixmaps: dict[str, QPixmap] = {}


def pixmap(path: str) -> QPixmap:
    pm = _pixmaps.get(path)
    if pm is None:
        pm = QPixmap(path)
        _pixmaps[path] = pm
    return pm


class View:
    """Maps squares to widget pixels: s pixels per square, (ox, oy) = square at the widget origin."""

    def __init__(self, s: float, ox: float, oy: float):
        self.s, self.ox, self.oy = s, ox, oy

    def pt(self, x, y) -> QPointF:
        return QPointF((x - self.ox) * self.s, (y - self.oy) * self.s)

    def rect(self, r: QRectF) -> QRectF:
        return QRectF(self.pt(r.left(), r.top()), self.pt(r.right(), r.bottom()))

    def to_map(self, px, py) -> QPointF:
        return QPointF(px / self.s + self.ox, py / self.s + self.oy)

    def transform(self) -> QTransform:
        return QTransform(self.s, 0, 0, self.s, -self.ox * self.s, -self.oy * self.s)


class Overlay:
    """A live measurement: a ruler (a, b) or a template."""

    def __init__(self, kind, a=None, b=None, template: Template | None = None):
        self.kind, self.a, self.b, self.template = kind, a, b, template


# ---------------------------------------------------------------- map and fog

def draw_parts(p: QPainter, view: View, m: GameMap, image_path, focus: str | None = None):
    """Draw all map parts. With focus set (part editing), the other parts fade and the
    focused part also shows its cropped-away area faintly."""
    vt = view.transform()
    for part in m.parts:
        pm = pixmap(image_path(part.image))
        if pm.isNull():
            continue
        p.save()
        p.setWorldTransform(part.image_to_squares() * vt, True)
        if focus and part.id != focus:
            p.setOpacity(0.3)
        if focus and part.id == focus:
            p.setOpacity(0.3)
            p.drawPixmap(0, 0, pm)
            p.setOpacity(1.0)
        p.setClipRect(part.crop_rect(), Qt.IntersectClip)
        p.drawPixmap(0, 0, pm)
        p.restore()


def draw_fog(p: QPainter, view: View, fog: Fog, dm: bool):
    target = view.rect(fog.rect())
    if dm:
        tinted = QImage(fog.image.size(), QImage.Format_ARGB32_Premultiplied)
        tinted.fill(style.FOG_DM)
        q = QPainter(tinted)
        q.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        q.drawImage(0, 0, fog.image)
        q.end()
        p.save()
        p.setOpacity(0.55)
        p.drawImage(target, tinted)
        p.restore()
    else:
        p.drawImage(target, fog.image)


def draw_grid(p: QPainter, view: View, area: QRectF):
    tl, br = view.to_map(area.left(), area.top()), view.to_map(area.right(), area.bottom())
    if view.s < 4:
        return
    p.save()
    # a dark line under a light one stays visible on bright parchment and on dark maps alike
    for pen in (QPen(QColor(0, 0, 0, 90), 2.2), QPen(QColor(250, 199, 117, 220), 1)):
        p.setPen(pen)
        for x in range(math.floor(tl.x()), math.ceil(br.x()) + 1):
            p.drawLine(view.pt(x, tl.y()), view.pt(x, br.y()))
        for y in range(math.floor(tl.y()), math.ceil(br.y()) + 1):
            p.drawLine(view.pt(tl.x(), y), view.pt(br.x(), y))
    p.restore()


# ---------------------------------------------------------------- text helpers

def _lw(view: View, f: float, minimum=1.0) -> float:
    return max(minimum, view.s * f)


def draw_plate(p: QPainter, center: QPointF, angle: float, text: str, font, border: QColor,
               fg: QColor, double=False, bg: QColor | None = None):
    fm = QFontMetricsF(font)
    w, h = fm.horizontalAdvance(text), fm.height()
    pad = h * 0.35
    p.save()
    p.translate(center)
    p.rotate(angle)
    box = QRectF(-w / 2 - pad, -h / 2 - pad * 0.4, w + 2 * pad, h + pad * 0.8)
    p.setPen(QPen(border, max(1.0, h * 0.08)))
    p.setBrush(bg if bg is not None else style.PARCHMENT)
    p.drawRect(box)
    if double:
        inset = max(1.5, h * 0.12)
        p.setPen(QPen(border, max(0.6, h * 0.04)))
        p.setBrush(Qt.NoBrush)
        p.drawRect(box.adjusted(inset, inset, -inset, -inset))
    p.setFont(font)
    p.setPen(fg)
    p.drawText(box, Qt.AlignCenter, text)
    p.restore()


def draw_ring_text(p: QPainter, c: QPointF, radius: float, text: str, font, color: QColor):
    """Write text four times along a circle, each copy facing outward to one table side."""
    fm = QFontMetricsF(font)
    width = fm.horizontalAdvance(text)
    if radius <= 0 or width >= radius * math.pi / 2:
        return False
    halo = QPen(style.PARCHMENT, max(1.5, fm.height() * 0.22), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    for mid_deg in (-90, 0, 90, 180):
        theta = math.radians(mid_deg) - width / radius / 2
        for ch in text:
            a = fm.horizontalAdvance(ch)
            th = theta + a / 2 / radius
            path = QPainterPath()
            path.addText(-a / 2, 0, font, ch)
            p.save()
            p.translate(c.x() + radius * math.cos(th), c.y() + radius * math.sin(th))
            p.rotate(math.degrees(th) + 90)
            p.strokePath(path, halo)
            p.fillPath(path, color)
            p.restore()
            theta += a / radius
    return True


def _diamond(p: QPainter, c: QPointF, r: float, fill: QColor, edge: QColor | None = None):
    poly = QPolygonF([QPointF(c.x(), c.y() - r), QPointF(c.x() + r, c.y()),
                      QPointF(c.x(), c.y() + r), QPointF(c.x() - r, c.y())])
    p.setPen(QPen(edge, max(1.0, r * 0.25)) if edge else Qt.NoPen)
    p.setBrush(fill)
    p.drawPolygon(poly)


def _haloed(p: QPainter, shape: QPainterPath, view: View, color: QColor, width: float):
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 230), width * 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(shape)
    p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(shape)


# ---------------------------------------------------------------- measurements

def draw_ruler(p: QPainter, view: View, a: QPointF, b: QPointF, rule: str):
    n = grid_distance(a.x(), a.y(), b.x(), b.y(), rule)
    pa, pb = view.pt(a.x(), a.y()), view.pt(b.x(), b.y())
    w = _lw(view, 0.07, 2)
    path = QPainterPath(pa)
    path.lineTo(pb)
    _haloed(p, path, view, style.RULER, w)
    for i in range(1, n):
        t = i / n
        c = pa + (pb - pa) * t
        p.setPen(QPen(QColor("white"), w * 0.5))
        p.setBrush(style.RULER)
        p.drawEllipse(c, w * 1.3, w * 1.3)
    for c in (pa, pb):
        _diamond(p, c, w * 3, style.RULER, QColor("white"))
    if n == 0:
        return
    text = f"{n * FT_PER_SQUARE} ft · {n} sq"
    font = style.display_font(_lw(view, 0.3, 11))
    ang = math.degrees(math.atan2(pb.y() - pa.y(), pb.x() - pa.x()))
    if ang > 90 or ang <= -90:
        ang += 180
    mid = (pa + pb) / 2
    off = QFontMetricsF(font).height() * 1.1
    rad = math.radians(ang - 90)
    normal = QPointF(math.cos(rad), math.sin(rad))
    draw_plate(p, mid + normal * off, ang, text, font, style.RULER, style.RULER_TEXT)
    draw_plate(p, mid - normal * off, ang + 180, text, font, style.RULER, style.RULER_TEXT)


def template_outline(view: View, t: Template) -> QPainterPath:
    L = t.size_ft / FT_PER_SQUARE
    path = QPainterPath()
    if t.shape in ("sphere", "range"):
        path.addEllipse(view.pt(t.x, t.y), L * view.s, L * view.s)
        return path
    if t.shape == "cube":
        sx = 1 if t.dx >= t.x else -1
        sy = 1 if t.dy >= t.y else -1
        path.addRect(QRectF(view.pt(t.x, t.y), view.pt(t.x + sx * L, t.y + sy * L)).normalized())
        return path
    vx, vy = t.dx - t.x, t.dy - t.y
    n = math.hypot(vx, vy) or 1.0
    ux, uy = vx / n, vy / n
    half = L / 2 if t.shape == "cone" else 0.5
    start_half = 0 if t.shape == "cone" else 0.5
    pts = [(t.x - uy * start_half, t.y + ux * start_half),
           (t.x + ux * L - uy * half, t.y + uy * L + ux * half),
           (t.x + ux * L + uy * half, t.y + uy * L - ux * half),
           (t.x + uy * start_half, t.y - ux * start_half)]
    path.addPolygon(QPolygonF([view.pt(x, y) for x, y in pts]))
    path.closeSubpath()
    return path


def draw_template(p: QPainter, view: View, t: Template):
    L = t.size_ft / FT_PER_SQUARE
    fill = QColor(style.GOLD_LIGHT)
    fill.setAlpha(90)
    p.setPen(QPen(style.GOLD, _lw(view, 0.02, 0.6)))
    p.setBrush(fill)
    for x, y in template_squares(t):
        p.drawRect(QRectF(view.pt(x, y), view.pt(x + 1, y + 1)))
    w = _lw(view, 0.06, 1.5)
    outline = template_outline(view, t)
    _haloed(p, outline, view, style.BROWN, w)
    origin = view.pt(t.x, t.y)
    text = f"{t.size_ft} ft"
    font = style.display_font(_lw(view, 0.32, 11))
    if t.shape in ("sphere", "range"):
        if t.shape == "sphere" and L * view.s > 12:
            p.setPen(QPen(style.BROWN, w * 0.45, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(origin, L * view.s - w * 3, L * view.s - w * 3)
        radius = L * view.s + w * 2
        if not draw_ring_text(p, origin, radius, f"· {text} ·", font, style.INK_TEXT):
            draw_ring_text(p, origin, radius, text, font, style.INK_TEXT)
    elif t.shape == "cube":
        r = outline.boundingRect()
        c = r.center()
        gap = QFontMetricsF(font).height() * 0.9
        draw_plate(p, QPointF(c.x(), r.bottom() + gap), 0, text, font, style.BROWN, style.INK_TEXT)
        draw_plate(p, QPointF(c.x(), r.top() - gap), 180, text, font, style.BROWN, style.INK_TEXT)
        draw_plate(p, QPointF(r.left() - gap, c.y()), 90, text, font, style.BROWN, style.INK_TEXT)
        draw_plate(p, QPointF(r.right() + gap, c.y()), -90, text, font, style.BROWN, style.INK_TEXT)
    else:
        n = math.hypot(t.dx - t.x, t.dy - t.y) or 1.0
        ux, uy = (t.dx - t.x) / n, (t.dy - t.y) / n
        mid = view.pt(t.x + ux * L * 0.6, t.y + uy * L * 0.6)
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90 or ang <= -90:
            ang += 180
        off = QFontMetricsF(font).height() * 1.0
        rad = math.radians(ang - 90)
        normal = QPointF(math.cos(rad), math.sin(rad)) * off
        draw_plate(p, mid + normal, ang, text, font, style.BROWN, style.INK_TEXT)
        draw_plate(p, mid - normal, ang + 180, text, font, style.BROWN, style.INK_TEXT)
    _diamond(p, origin, w * 2.6, style.BROWN, QColor("white"))


def draw_overlay(p: QPainter, view: View, o: Overlay | None, rule: str):
    if o is None:
        return
    if o.kind == "ruler" and o.a is not None and o.b is not None:
        draw_ruler(p, view, o.a, o.b, rule)
    elif o.kind == "template" and o.template is not None:
        draw_template(p, view, o.template)


# ---------------------------------------------------------------- marks

def _color(hex_: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def draw_mark(p: QPainter, view: View, k: TableMark, image_path, dm_view=False):
    """Draw a text, shape or image object. DM-only marks show faded with a tag on the DM screen."""
    p.save()
    if dm_view and k.dm_only:
        p.setOpacity(0.5)
    lw = _lw(view, 0.06, 1.5)
    stroke = QPen(_color(k.stroke), lw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if k.stroke else Qt.NoPen
    fill = _color(k.fill, k.opacity) if k.fill else Qt.NoBrush
    if k.kind in ("line", "arrow"):
        a, b = view.pt(k.x, k.y), view.pt(k.x2, k.y2)
        color = _color(k.stroke or "#2C2C2A")
        path = QPainterPath(a)
        path.lineTo(b)
        _haloed(p, path, view, color, lw)
        if k.kind == "arrow" and (a - b).manhattanLength() > 1:
            ang = math.atan2(b.y() - a.y(), b.x() - a.x())
            size = _lw(view, 0.3, 8)
            head = QPolygonF([b + QPointF(math.cos(ang), math.sin(ang)) * lw,
                              b - QPointF(math.cos(ang - 0.45), math.sin(ang - 0.45)) * size,
                              b - QPointF(math.cos(ang + 0.45), math.sin(ang + 0.45)) * size])
            p.setPen(QPen(QColor("white"), lw * 0.8))
            p.setBrush(color)
            p.drawPolygon(head)
    else:
        p.translate(view.pt(k.x, k.y))
        p.rotate(k.rotation)
        if k.kind == "text":
            font = style.note_font(max(1.0, k.text_size * view.s))
            color = _color(k.stroke or "#2C2C2A")
            draw_plate(p, QPointF(0, 0), 0, k.text, font, color, color, double=True,
                       bg=_color(k.fill or "#F4EBD6", k.opacity))
        else:
            r = QRectF(-k.w * view.s / 2, -k.h * view.s / 2, k.w * view.s, k.h * view.s)
            if k.kind == "image":
                pm = pixmap(image_path(k.image)) if k.image else QPixmap()
                p.setOpacity(p.opacity() * k.opacity)
                if pm.isNull():
                    p.setPen(QPen(style.RULER, 1, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(r)
                else:
                    p.drawPixmap(r, pm, QRectF(pm.rect()))
            else:
                p.setPen(stroke)
                p.setBrush(fill)
                if k.kind == "rect":
                    p.drawRect(r)
                elif k.kind == "circle":
                    p.drawEllipse(r)
                elif k.kind == "triangle":
                    p.drawPolygon(QPolygonF([QPointF(0, r.top()), r.bottomRight(), r.bottomLeft()]))
    p.restore()


def draw_dm_tag(p: QPainter, view: View, k: TableMark):
    """Small 'DM' label above a DM-only mark, drawn after all marks so nothing covers it."""
    b = view.rect(marks.bounds(k))
    p.setFont(style.display_font(11))
    tag = QRectF(b.left(), b.top() - 16, 28, 15)
    p.setPen(Qt.NoPen)
    p.setBrush(style.BROWN)
    p.drawRect(tag)
    p.setPen(QColor("white"))
    p.drawText(tag, Qt.AlignCenter, "DM")


def draw_remark(p: QPainter, view: View, r: Remark):
    c = view.pt(r.x, r.y)
    rad = _lw(view, 0.2, 5)
    seal = style.GOLD if r.link else style.RULER
    p.setPen(QPen(seal.darker(140), rad * 0.3))
    p.setBrush(seal)
    p.drawEllipse(c, rad, rad)
    text = ("→ " if r.link else "") + r.text
    font = style.note_font(max(11, view.s * 0.28))
    fm = QFontMetricsF(font)
    w = fm.horizontalAdvance(text)
    box = QRectF(c.x() + rad * 1.6, c.y() - fm.height() * 0.65, w + 8, fm.height() * 1.3)
    p.setPen(QPen(QColor("#C9B58E"), 1))
    p.setBrush(style.PARCHMENT)
    p.drawRect(box)
    p.setFont(font)
    p.setPen(style.INK)
    p.drawText(box, Qt.AlignCenter, text)


def draw_marker(p: QPainter, view: View, k: Marker, active: bool):
    c = view.pt(k.x, k.y)
    r = _lw(view, 0.38, 7)
    p.setPen(QPen(style.MARKER, r * (0.3 if active else 0.18)))
    p.setBrush(style.MARKER_FILL)
    p.drawEllipse(c, r, r)
    font = style.display_font(r * 1.1)
    p.setFont(font)
    p.setPen(style.MARKER.darker(130))
    p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, (k.name or "P")[:1].upper())


def draw_ghost(p: QPainter, view: View, x, y):
    c = view.pt(x, y)
    r = view.s * 0.44
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 160), _lw(view, 0.07, 2)))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(style.GHOST, _lw(view, 0.05, 1.5), Qt.DashLine))
    p.drawEllipse(c, r, r)


def draw_tiles(p: QPainter, view: View, tiles: list[Tile], current_id):
    font = style.display_font(max(11, min(16, view.s * 0.45)))
    fm = QFontMetricsF(font)
    for t in tiles:
        r = view.rect(t.rect())
        current = t.id == current_id
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(style.GOLD, 2.5 if current else 1, Qt.SolidLine if current else Qt.DashLine))
        p.drawRect(r)
        label = t.name + (" · on table" if current else "")
        box = QRectF(r.left() + 1, r.top() + 1, fm.horizontalAdvance(label) + 8, fm.height() + 2)
        p.setPen(Qt.NoPen)
        p.setBrush(style.PARCHMENT_HL)
        p.drawRect(box)
        p.setFont(font)
        p.setPen(style.INK_TEXT)
        p.drawText(box, Qt.AlignCenter, label)


# ---------------------------------------------------------------- whole views

def render_player(p: QPainter, area: QRectF, state: PlayerState, image_path, overlay: Overlay | None,
                  rule: str, pps: float | None = None, panic=False) -> View | None:
    """Draw the table view of `state` into area. pps fixes the physical scale on the projector."""
    p.fillRect(area, QColor("black"))
    tile, m = state.tile, state.map
    if panic or tile is None or m is None:
        return None
    s = min(area.width() / tile.w, area.height() / tile.h)
    if pps:
        s = min(s, pps)
    left = area.left() + (area.width() - tile.w * s) / 2
    top = area.top() + (area.height() - tile.h * s) / 2
    view = View(s, tile.x - left / s, tile.y - top / s)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.setClipRect(view.rect(tile.rect()))
    draw_parts(p, view, m, image_path)
    for t in m.templates:
        draw_template(p, view, t)
    if state.fog:
        draw_fog(p, view, state.fog, dm=False)
    for k in m.marks:
        c = marks.center(k)
        if not k.dm_only and (not state.fog or not state.fog.is_fogged(c.x(), c.y())):
            draw_mark(p, view, k, image_path)
    for gx, gy in state.ghosts:
        if tile.contains(gx, gy):
            draw_ghost(p, view, gx, gy)
    draw_overlay(p, view, overlay, rule)
    p.restore()
    return view
