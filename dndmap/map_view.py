"""The DM's interactive map: select tool, fog tools, measuring, marks and map preparation."""
from __future__ import annotations

import copy
import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QLabel, QMenu, QWidget

from dndmap import marks, render, style
from dndmap.geometry import template_contains
from dndmap.model import Marker, TableMark, Template, Tile, new_id
from dndmap.render import Overlay, View

PREP_TOOLS = ("tile",)
HANDLE_PX = 7


def square_center(p: QPointF) -> QPointF:
    return QPointF(math.floor(p.x()) + 0.5, math.floor(p.y()) + 0.5)


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _snap_rect(a: QPointF, b: QPointF) -> QRectF:
    """Rectangle between two points with its corners on grid lines, at least one square."""
    x0, x1 = sorted((a.x(), b.x()))
    y0, y1 = sorted((a.y(), b.y()))
    x0, y0 = math.floor(x0), math.floor(y0)
    x1, y1 = max(x0 + 1, math.ceil(x1)), max(y0 + 1, math.ceil(y1))
    return QRectF(x0, y0, x1 - x0, y1 - y0)


class MapView(QWidget):
    cursor_moved = Signal(float, float)
    selection_changed = Signal()

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.s, self.ox, self.oy = 24.0, -2.0, -2.0
        self.tool = "select"
        self.overlay: Overlay | None = None
        self.show_on_table = False
        self.show_grid = False
        self.poly: list[tuple[int, int]] = []
        self.drag: dict | None = None
        self.hover: QPointF | None = None
        self.selection: list[tuple[str, object]] = []
        self.clipboard: list[tuple[str, object]] = []
        self.grid_mark = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 240)
        self.toast = QLabel(self)
        self.toast.setStyleSheet(
            f"background:#F4EBD6;border:1px solid #854F0B;padding:6px 12px;"
            f"font-family:'{style.display_family()}';font-size:13px;color:#2C2C2A;")
        self.toast.hide()
        self._toast_timer = QTimer(self, singleShot=True, timeout=self.toast.hide)

    # ================================================================ helpers
    @property
    def adv(self):
        return self.win.adv

    def view(self) -> View:
        return View(self.s, self.ox, self.oy)

    def to_map(self, pos) -> QPointF:
        return self.view().to_map(pos.x(), pos.y())

    def show_toast(self, text: str, ms=8000):
        self.toast.setText(text)
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2, 12)
        self.toast.show()
        self.toast.raise_()
        self._toast_timer.start(ms)

    def center_on(self, rect: QRectF, margin=1.0):
        if rect.isNull() or rect.width() <= 0:
            return
        self.s = max(2.0, min(self.width() / (rect.width() + 2 * margin),
                              self.height() / (rect.height() + 2 * margin)))
        self.ox = rect.center().x() - self.width() / 2 / self.s
        self.oy = rect.center().y() - self.height() / 2 / self.s
        self.update()

    def center_on_point(self, x, y):
        self.ox = x - self.width() / 2 / self.s
        self.oy = y - self.height() / 2 / self.s
        self.update()

    def set_tool(self, tool: str):
        self.tool = tool
        self.poly = []
        self.drag = None
        self.grid_mark = False
        self.setCursor(Qt.ArrowCursor if tool == "select" else Qt.CrossCursor)
        self.update()

    # ================================================================ selection
    def set_selection(self, items):
        self.selection = list(items)
        self.grid_mark = False
        self.selection_changed.emit()
        self.update()

    def selected_part(self):
        if self.win.prep_mode and len(self.selection) == 1 and self.selection[0][0] == "part":
            return self.selection[0][1]
        return None

    def _lists(self):
        m = self.adv.map()
        if not m:
            return {}
        return {"mark": m.marks, "remark": m.remarks, "template": m.templates, "tile": m.tiles,
                "part": m.parts, "marker": self.adv.markers}

    def validate_selection(self):
        """Drop selected items that no longer exist (after undo, delete or a map switch)."""
        lists = self._lists()
        keep = [(k, o) for k, o in self.selection if any(x is o for x in lists.get(k, []))]
        if len(keep) != len(self.selection):
            self.selection = keep
            self.selection_changed.emit()

    def is_locked(self, kind, obj) -> bool:
        if kind == "part":
            return obj.locked or not self.win.prep_mode
        if kind == "tile":
            return not self.win.prep_mode
        return getattr(obj, "locked", False)

    def item_at(self, mp: QPointF):
        """Topmost selectable item under a map point."""
        m = self.adv.map()
        if not m:
            return None
        tol = max(0.2, 8 / self.s)
        for r in m.remarks:
            if _dist(mp, QPointF(r.x, r.y)) < tol * 1.6:
                return ("remark", r)
        for k in self.adv.markers:
            if k.map == m.id and _dist(mp, QPointF(k.x, k.y)) < max(0.45, tol):
                return ("marker", k)
        for k in reversed(m.marks):
            if marks.contains(k, mp, tol):
                return ("mark", k)
        for t in reversed(m.templates):
            if template_contains(t, mp.x(), mp.y()) or _dist(mp, QPointF(t.x, t.y)) < tol:
                return ("template", t)
        if self.win.prep_mode:
            for t in m.tiles:
                r = t.rect()
                near = (r.adjusted(-tol, -tol, tol, tol).contains(mp)
                        and not r.adjusted(tol, tol, -tol, -tol).contains(mp))
                label = QRectF(r.left(), r.top(), max(1.5, 60 / self.s), max(0.6, 18 / self.s)).contains(mp)
                if near or label:
                    return ("tile", t)
            for part in reversed(m.parts):
                if part.bounds().contains(mp):
                    return ("part", part)
        return None

    def _handle_at(self, pos) -> tuple[str, object, str] | None:
        """Resize/rotate handle of the single selected mark, or crop handle of the selected part."""
        if len(self.selection) != 1:
            return None
        kind, obj = self.selection[0]
        view = self.view()
        if kind == "mark" and not obj.locked:
            for name, hp in marks.handles(obj, 22 / self.s).items():
                if _dist(view.pt(hp.x(), hp.y()), pos) <= HANDLE_PX + 2:
                    return ("mark", obj, name)
        part = self.selected_part()
        if part is not None and not part.locked:
            for name, hp in self._crop_handles(part).items():
                if _dist(view.pt(hp.x(), hp.y()), pos) <= HANDLE_PX + 2:
                    return ("part", part, name)
        return None

    @staticmethod
    def _crop_handles(part) -> dict[str, QPointF]:
        b = part.bounds()
        cx, cy = b.center().x(), b.center().y()
        return {"nw": b.topLeft(), "n": QPointF(cx, b.top()), "ne": b.topRight(), "e": QPointF(b.right(), cy),
                "se": b.bottomRight(), "s": QPointF(cx, b.bottom()), "sw": b.bottomLeft(), "w": QPointF(b.left(), cy)}

    # ---------------------------------------------------------------- selection operations
    def delete_selection(self):
        lists = self._lists()
        doomed = [(k, o) for k, o in self.selection if not self.is_locked(k, o)]
        if not doomed:
            if self.selection:
                self.show_toast("Locked items can't be deleted. Unlock them first.", 3000)
            return
        self.adv.push_undo()
        for k, o in doomed:
            lst = lists.get(k)
            if lst is not None and any(x is o for x in lst):
                lst.remove(o)
            if k == "marker" and self.adv.active_marker == o.id:
                self.adv.active_marker = self.adv.markers[0].id if self.adv.markers else None
        self.set_selection([])
        self.adv.touch(structure=True)

    def copy_selection(self):
        self.clipboard = [(k, copy.deepcopy(o)) for k, o in self.selection if k in ("mark", "remark", "template")]
        if self.clipboard:
            self.win.statusBar().showMessage(f"Copied {len(self.clipboard)} item(s).", 2000)

    def paste(self):
        m = self.adv.map()
        if not m or not self.clipboard:
            return
        pts = [self._anchor(k, o) for k, o in self.clipboard]
        cx = sum(p.x() for p in pts) / len(pts)
        cy = sum(p.y() for p in pts) / len(pts)
        target = square_center(self.hover) if self.hover is not None else QPointF(cx + 1, cy + 1)
        dx, dy = target.x() - square_center(QPointF(cx, cy)).x(), target.y() - square_center(QPointF(cx, cy)).y()
        self.adv.push_undo()
        pasted = []
        for k, o in self.clipboard:
            o = copy.deepcopy(o)
            o.id = new_id()
            self._move_obj(k, o, dx, dy)
            {"mark": m.marks, "remark": m.remarks, "template": m.templates}[k].append(o)
            pasted.append((k, o))
        self.set_selection(pasted)
        self.adv.touch(structure=True)

    def nudge(self, dx: int, dy: int) -> bool:
        movable = [(k, o) for k, o in self.selection if not self.is_locked(k, o)]
        if not movable:
            return False
        self.adv.push_undo("nudge")
        for k, o in movable:
            self._move_obj(k, o, dx, dy)
        self.adv.touch(structure=any(k in ("tile", "part") for k, _ in movable))
        return True

    def reorder(self, to_front: bool):
        m = self.adv.map()
        if not m:
            return
        self.adv.push_undo()
        for kind, lst in (("mark", m.marks), ("part", m.parts)):
            chosen = [o for k, o in self.selection if k == kind]
            if not chosen:
                continue
            rest = [o for o in lst if not any(o is c for c in chosen)]
            lst[:] = rest + chosen if to_front else chosen + rest
        self.adv.touch(structure=True)

    @staticmethod
    def _anchor(kind, o) -> QPointF:
        if kind == "mark":
            return marks.center(o)
        if kind == "tile":
            return QPointF(o.x, o.y)
        if kind == "part":
            return QPointF(o.gx, o.gy)
        return QPointF(o.x, o.y)

    @staticmethod
    def _move_obj(kind, o, dx, dy):
        if kind == "mark":
            marks.move(o, dx, dy)
        elif kind == "template":
            o.x += dx
            o.y += dy
            o.dx += dx
            o.dy += dy
        elif kind == "tile":
            o.x += round(dx)
            o.y += round(dy)
        elif kind == "part":
            o.gx += round(dx)
            o.gy += round(dy)
        else:
            o.x += dx
            o.y += dy

    @staticmethod
    def _position(kind, o):
        if kind == "tile":
            return (o.x, o.y)
        if kind == "part":
            return (o.gx, o.gy)
        if kind in ("mark", "template"):
            return (o.x, o.y, o.x2 if kind == "mark" else o.dx, o.y2 if kind == "mark" else o.dy)
        return (o.x, o.y)

    @staticmethod
    def _restore_position(kind, o, pos):
        if kind == "tile":
            o.x, o.y = pos
        elif kind == "part":
            o.gx, o.gy = pos
        elif kind == "mark":
            o.x, o.y, o.x2, o.y2 = pos
        elif kind == "template":
            o.x, o.y, o.dx, o.dy = pos
        else:
            o.x, o.y = pos

    def _snapped_delta(self, kind, o, dx, dy):
        if kind == "mark":
            return marks.snap_delta(o, dx, dy)
        if kind in ("tile", "part"):
            return round(dx), round(dy)
        if kind == "template" and o.shape != "range":
            return round(o.x + dx) - o.x, round(o.y + dy) - o.y
        c = square_center(QPointF(o.x + dx, o.y + dy))
        return c.x() - o.x, c.y() - o.y

    # ================================================================ overlay (measurements)
    def set_overlay(self, o: Overlay | None):
        self.overlay = o
        self.sync_table_overlay()

    def set_show_on_table(self, on: bool):
        self.show_on_table = on
        self.sync_table_overlay()

    def sync_table_overlay(self):
        self.adv.live_overlay = self.overlay if self.show_on_table else None
        self.adv.changed.emit()

    def clear(self) -> bool:
        """Clear what is in progress. Returns False when there was nothing to clear."""
        had = bool(self.poly or self.drag or self.overlay or self.grid_mark or self.selection)
        self.poly = []
        self.drag = None
        self.grid_mark = False
        if self.selection:
            self.set_selection([])
        self.set_overlay(None)
        return had

    def pin_overlay(self):
        m = self.adv.map()
        if not m or not self.overlay or self.overlay.kind != "template":
            return False
        self.adv.push_undo()
        t = copy.deepcopy(self.overlay.template)
        t.id = new_id()
        m.templates.append(t)
        self.set_overlay(None)
        self.adv.touch(structure=True)
        return True

    # ================================================================ painting
    def paintEvent(self, _):
        self.validate_selection()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#E6E1D5"))
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.drag is None or self.drag["kind"] != "pan")
        adv, view = self.adv, self.view()
        m = adv.map()
        if m is None or not m.parts:
            p.setFont(style.display_font(18))
            p.setPen(style.INK_TEXT)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Import a map image or PDF\nFile › Import map (Ctrl+I)")
            if m is None:
                return
        part_focus = self.selected_part()
        render.draw_parts(p, view, m, adv.image_path, focus=part_focus.id if part_focus else None)
        if self.show_grid or self.grid_mark:
            render.draw_grid(p, view, QRectF(self.rect()))
        for t in m.templates:
            render.draw_template(p, view, t)
        fog = adv.map_fog()
        if fog and m.parts and part_focus is None:
            render.draw_fog(p, view, fog, dm=True)
        for k in m.marks:
            render.draw_mark(p, view, k, adv.image_path, dm_view=True)
        for k in m.marks:
            if k.dm_only:
                render.draw_dm_tag(p, view, k)
        for r in m.remarks:
            render.draw_remark(p, view, r)
        tile = adv.table_tile()
        for k in adv.markers:
            if k.map == m.id:
                render.draw_marker(p, view, k, k.id == adv.active_marker)
                if adv.ghosts_pending and tile and tile.contains(k.x, k.y):
                    render.draw_ghost(p, view, k.x, k.y)
        render.draw_tiles(p, view, m.tiles, adv.current_tile.get(m.id))
        render.draw_overlay(p, view, self.overlay, self.win.setup.rule)
        self._paint_selection(p, view)
        self._paint_tool_feedback(p, view)

    def _handle(self, p: QPainter, c: QPointF, round_=False):
        p.setPen(QPen(style.GOLD, 1.5))
        p.setBrush(QColor("white"))
        if round_:
            p.drawEllipse(c, HANDLE_PX - 1, HANDLE_PX - 1)
        else:
            p.drawRect(QRectF(c.x() - HANDLE_PX / 2 - 1, c.y() - HANDLE_PX / 2 - 1, HANDLE_PX + 2, HANDLE_PX + 2))

    def _paint_selection(self, p: QPainter, view: View):
        single = len(self.selection) == 1
        for kind, o in self.selection:
            locked = self.is_locked(kind, o)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(style.GOLD, 1.5, Qt.DashLine))
            if kind == "mark":
                pts = [view.pt(c.x(), c.y()) for c in marks.corners(o)]
                if len(pts) == 2:
                    p.drawLine(pts[0], pts[1])
                else:
                    p.drawPolygon(QPolygonF(pts))
                if single and not locked:
                    hs = marks.handles(o, 22 / self.s)
                    if "rot" in hs:
                        top = hs.get("n") or (hs["nw"] + hs["ne"]) / 2
                        p.setPen(QPen(style.GOLD, 1.2))
                        p.drawLine(view.pt(top.x(), top.y()), view.pt(hs["rot"].x(), hs["rot"].y()))
                    for name, hp in hs.items():
                        self._handle(p, view.pt(hp.x(), hp.y()), round_=name in ("rot", "p1", "p2"))
            elif kind == "part":
                r = view.rect(o.bounds())
                p.setPen(QPen(style.GOLD, 2))
                p.drawRect(r)
                if single and not locked:
                    for hp in self._crop_handles(o).values():
                        self._handle(p, view.pt(hp.x(), hp.y()))
            elif kind == "tile":
                p.setPen(QPen(style.GOLD, 4))
                p.drawRect(view.rect(o.rect()))
            elif kind == "template":
                p.drawRect(view.rect(QRectF(o.x - 0.5, o.y - 0.5, 1, 1)))
            else:
                c = view.pt(o.x, o.y)
                rad = max(10.0, 0.55 * view.s)
                p.drawEllipse(c, rad, rad)
            if locked and kind in ("mark", "part"):
                b = view.rect(marks.bounds(o) if kind == "mark" else o.bounds())
                p.setFont(style.display_font(11))
                tag = QRectF(b.right() - 52, b.top() - 16, 52, 15)
                p.setPen(Qt.NoPen)
                p.setBrush(style.INK)
                p.drawRect(tag)
                p.setPen(QColor("white"))
                p.drawText(tag, Qt.AlignCenter, "locked")

    def _paint_tool_feedback(self, p: QPainter, view: View):
        h = self.hover
        if self.tool in ("reveal", "hide") and h is not None:
            r = self.win.brush_size() * view.s
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("white"), 3))
            p.drawEllipse(view.pt(h.x(), h.y()), r, r)
            p.setPen(QPen(style.BROWN, 1.2, Qt.DashLine))
            p.drawEllipse(view.pt(h.x(), h.y()), r, r)
        if self.tool == "polygon" and self.poly:
            pts = [view.pt(x, y) for x, y in self.poly]
            if h is not None:
                pts.append(view.pt(round(h.x()), round(h.y())))
            p.setPen(QPen(style.BROWN, 2, Qt.DashLine))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
            p.setBrush(style.BROWN)
            for c in pts[:len(self.poly)]:
                p.drawEllipse(c, 4, 4)
        d = self.drag
        if not d:
            return
        if d["kind"] in ("band", "grid"):
            r = QRectF(view.pt(d["a"].x(), d["a"].y()), view.pt(d["b"].x(), d["b"].y())).normalized()
            p.setBrush(QColor(239, 159, 39, 40))
            p.setPen(QPen(QColor("white"), 3))
            p.drawRect(r)
            p.setPen(QPen(style.BROWN, 1.5, Qt.DashLine))
            p.drawRect(r)
            if d["kind"] == "grid":
                sq = QRectF(d["a"], d["b"]).normalized()
                label = f"≈ {max(1, round(sq.width()))} × {max(1, round(sq.height()))} squares by the current grid"
                render.draw_plate(p, QPointF(r.center().x(), r.top() - 16), 0, label,
                                  style.display_font(13), style.BROWN, style.INK_TEXT)
        elif d["kind"] == "fogrect":
            r = _snap_rect(d["a"], d["b"])
            hide = bool(self.win.app_modifiers() & Qt.ShiftModifier)
            p.setBrush(QColor(95, 94, 90, 110) if hide else QColor(255, 255, 255, 90))
            p.setPen(QPen(style.BROWN, 2, Qt.DashLine))
            p.drawRect(view.rect(r))
        elif d["kind"] == "place":
            render.draw_mark(p, view, d["mark"], self.adv.image_path, dm_view=True)

    # ================================================================ mouse
    def wheelEvent(self, e):
        pos = e.position()
        before = self.to_map(pos)
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.s = max(2.0, min(400.0, self.s * factor))
        self.ox = before.x() - pos.x() / self.s
        self.oy = before.y() - pos.y() / self.s
        self.update()

    def mousePressEvent(self, e):
        self.setFocus()     # hotkeys (arrows, Delete) go to the map, not a side-panel field
        pos = e.position()
        mp = self.to_map(pos)
        if e.button() in (Qt.MiddleButton, Qt.RightButton):
            self.drag = {"kind": "pan", "start": pos, "ox": self.ox, "oy": self.oy,
                         "button": e.button(), "moved": False}
            return
        if e.button() != Qt.LeftButton:
            return
        adv, m, t = self.adv, self.adv.map(), self.tool
        if m is None:
            return
        shift = bool(e.modifiers() & Qt.ShiftModifier)
        if self.grid_mark and self.selected_part() is not None:
            self.drag = {"kind": "grid", "part": self.selected_part(), "a": mp, "b": mp}
        elif t == "select":
            self._press_select(pos, mp, shift)
        elif t in ("reveal", "hide"):
            fog = adv.map_fog()
            adv.push_undo()
            fog.paint_circle(mp.x(), mp.y(), self.win.brush_size(), t == "reveal")
            self.drag = {"kind": "brush", "last": mp}
            adv.touch()
        elif t == "fogrect":
            self.drag = {"kind": "fogrect", "a": mp, "b": mp}
        elif t == "polygon":
            pt = (round(mp.x()), round(mp.y()))
            if len(self.poly) >= 3 and pt == self.poly[0]:
                self.close_polygon()
            elif not self.poly or pt != self.poly[-1]:
                self.poly.append(pt)
            self.update()
        elif t == "ruler":
            a = square_center(mp)
            self.set_overlay(Overlay("ruler", a, a))
            self.drag = {"kind": "ruler"}
        elif t == "range":
            a = square_center(mp)
            self.set_overlay(Overlay("template", template=Template(new_id(), "range", a.x(), a.y(), size_ft=5)))
            self.drag = {"kind": "range"}
        elif t == "template":
            shape, size = self.win.template_shape(), self.win.template_size()
            ox, oy = round(mp.x()), round(mp.y())
            tmpl = Template(new_id(), shape, ox, oy, ox + 1, oy + (1 if shape == "cube" else 0), size)
            self.set_overlay(Overlay("template", template=tmpl))
            self.drag = {"kind": "template"}
        elif t == "marker":
            adv.push_undo()
            k = adv.marker()
            if k is None:
                k = Marker(new_id(), "Party", m.id, 0, 0)
                adv.markers.append(k)
                adv.active_marker = k.id
            c = square_center(mp)
            k.map, k.x, k.y = m.id, c.x(), c.y()
            adv.touch(structure=True)
        elif t == "note":
            self.win.add_remark_at(mp)
        elif t == "mark":
            self._press_place(mp)
        elif t == "tile":
            tile = next((x for x in m.tiles if x.rect().contains(mp)), None)
            adv.push_undo()
            if tile is None:
                tw, th = self.win.setup.tile_size()
                tile = Tile(new_id(), self.win.next_tile_name(m), math.floor(mp.x() - tw / 2),
                            math.floor(mp.y() - th / 2), tw, th)
                m.tiles.append(tile)
                if not m.tile(adv.current_tile.get(m.id)):
                    adv.current_tile[m.id] = tile.id
                adv.touch(structure=True)
            self.drag = {"kind": "move", "start": mp, "items": [("tile", tile, (tile.x, tile.y))],
                         "primary": ("tile", tile, (tile.x, tile.y)), "pushed": True}

    def _press_select(self, pos, mp, shift):
        hit_handle = self._handle_at(pos) if not shift else None
        if hit_handle:
            kind, obj, name = hit_handle
            self.adv.push_undo()
            self.drag = {"kind": "handle" if kind == "mark" else "crop", "obj": obj, "name": name,
                         "orig": copy.deepcopy(obj)}
            return
        hit = self.item_at(mp)
        if hit is None:
            if not shift:
                self.set_selection([])
            self.drag = {"kind": "band", "a": mp, "b": mp, "add": shift}
            return
        in_sel = any(o is hit[1] for _, o in self.selection)
        if hit[0] == "part" and not in_sel and not shift:
            # map parts lie under everything: a click selects one, a drag draws a selection box
            self.set_selection([])
            self.drag = {"kind": "band", "a": mp, "b": mp, "add": False, "click": hit}
            return
        if shift:
            if in_sel:
                self.set_selection([(k, o) for k, o in self.selection if o is not hit[1]])
                return
            self.set_selection(self.selection + [hit])
        elif not in_sel:
            self.set_selection([hit])
        items = [(k, o, self._position(k, o)) for k, o in self.selection if not self.is_locked(k, o)]
        primary = next((it for it in items if it[1] is hit[1]), None)
        if items and primary:
            self.drag = {"kind": "move", "start": mp, "items": items, "primary": primary, "pushed": False}

    def _press_place(self, mp):
        props = self.win.palette_props()
        kind = props["kind"]
        if kind == "text":
            self.win.add_table_text_at(square_center(mp))
            return
        if kind == "image" and not props.get("image_src"):
            self.show_toast("Pick an object from the Objects list first.", 3000)
            return
        k = TableMark(new_id(), kind, mp.x(), mp.y(), mp.x(), mp.y(), fill=props["fill"], stroke=props["stroke"],
                      opacity=1.0 if kind == "image" else props["opacity"], dm_only=props["dm_only"])
        self.drag = {"kind": "place", "mark": k, "a": mp, "src": props.get("image_src")}

    def mouseMoveEvent(self, e):
        pos = e.position()
        mp = self.to_map(pos)
        self.hover = mp
        self.cursor_moved.emit(mp.x(), mp.y())
        d = self.drag
        snap = not (e.modifiers() & Qt.AltModifier)
        if d is None:
            if self.tool in ("reveal", "hide", "polygon"):
                self.update()
            return
        k = d["kind"]
        if k == "pan":
            delta = pos - d["start"]
            if abs(delta.x()) + abs(delta.y()) > 4:
                d["moved"] = True
            self.ox = d["ox"] - delta.x() / self.s
            self.oy = d["oy"] - delta.y() / self.s
        elif k == "brush":
            self.adv.map_fog().paint_stroke(d["last"], mp, self.win.brush_size(), self.tool == "reveal")
            d["last"] = mp
            self.adv.touch()
        elif k == "ruler":
            self.overlay.b = square_center(mp)
            self.sync_table_overlay()
        elif k == "range":
            t = self.overlay.template
            t.size_ft = 5 * max(1, round(math.hypot(mp.x() - t.x, mp.y() - t.y)))
            self.sync_table_overlay()
        elif k == "template":
            t = self.overlay.template
            if t.shape != "sphere" and math.hypot(mp.x() - t.x, mp.y() - t.y) > 0.2:
                t.dx, t.dy = mp.x(), mp.y()
            self.sync_table_overlay()
        elif k in ("band", "grid", "fogrect"):
            d["b"] = mp
        elif k == "place":
            self._update_placement(d, mp, snap)
        elif k == "move":
            self._drag_move(d, mp, snap)
        elif k == "handle":
            marks.apply_handle(d["obj"], d["orig"], d["name"], mp, snap)
            self.adv.touch()
            self.selection_changed.emit()
        elif k == "crop":
            self._drag_crop(d, mp, snap)
        self.update()

    def _drag_move(self, d, mp, snap):
        dx, dy = mp.x() - d["start"].x(), mp.y() - d["start"].y()
        if not d["pushed"]:
            if abs(dx) + abs(dy) < 0.15:
                return
            self.adv.push_undo()
            d["pushed"] = True
        pk, po, ppos = d["primary"]
        self._restore_position(pk, po, ppos)
        if snap:
            dx, dy = self._snapped_delta(pk, po, dx, dy)
        for kind, o, pos in d["items"]:
            self._restore_position(kind, o, pos)
            self._move_obj(kind, o, dx, dy)
        self.adv.touch()

    def _update_placement(self, d, mp, snap):
        k, a = d["mark"], d["a"]
        if k.kind in ("line", "arrow"):
            s0, s1 = (square_center(a), square_center(mp)) if snap else (a, mp)
            k.x, k.y, k.x2, k.y2 = s0.x(), s0.y(), s1.x(), s1.y()
            return
        r = _snap_rect(a, mp) if snap else QRectF(a, mp).normalized()
        k.x, k.y = r.center().x(), r.center().y()
        k.w, k.h = max(0.25, r.width()), max(0.25, r.height())
        if k.kind == "image":
            k.image = d.get("image") or ""
            if not k.image and d.get("src"):
                d["image"] = k.image = self.adv.object_image(d["src"])

    def _drag_crop(self, d, mp, snap):
        part, orig, name = d["obj"], d["orig"], d["name"]
        b = orig.bounds()
        x = round(mp.x()) if snap else mp.x()
        y = round(mp.y()) if snap else mp.y()
        left, top, right, bottom = b.left(), b.top(), b.right(), b.bottom()
        if "w" in name:
            left = min(x, right - 0.5)
        if "e" in name:
            right = max(x, left + 0.5)
        if "n" in name:
            top = min(y, bottom - 0.5)
        if "s" in name:
            bottom = max(y, top + 0.5)
        inv, _ = part.image_to_squares().inverted()
        img = inv.mapRect(QRectF(QPointF(left, top), QPointF(right, bottom))).intersected(QRectF(0, 0, part.w, part.h))
        if not img.isEmpty():
            part.crop = [img.x(), img.y(), img.width(), img.height()]
            self.adv.touch()

    def mouseReleaseEvent(self, e):
        d, self.drag = self.drag, None
        if d is None:
            return
        adv, m, k = self.adv, self.adv.map(), d["kind"]
        if k == "pan":
            if d["button"] == Qt.RightButton and not d["moved"]:
                self.context_menu(e.position())
        elif k == "brush":
            adv.check_reveal_popups()
            adv.touch()
        elif k == "fogrect":
            r = _snap_rect(d["a"], d["b"])
            adv.push_undo()
            adv.map_fog().paint_polygon([(r.left(), r.top()), (r.right(), r.top()),
                                         (r.right(), r.bottom()), (r.left(), r.bottom())],
                                        reveal=not (e.modifiers() & Qt.ShiftModifier))
            adv.check_reveal_popups()
            adv.touch()
        elif k == "band":
            r = QRectF(d["a"], d["b"]).normalized()
            if r.width() > 0.1 or r.height() > 0.1:
                found = self._items_in(r)
                base = self.selection if d["add"] else []
                self.set_selection(base + [it for it in found if not any(o is it[1] for _, o in base)])
            elif d.get("click"):
                self.set_selection([d["click"]])
        elif k == "grid":
            self.grid_mark = False
            self.win.align_grid(d["part"], d["a"], d["b"])
            self.selection_changed.emit()
        elif k == "place":
            mk = d["mark"]
            if _dist(d["a"], self.to_map(e.position())) < 0.3:
                self._place_default(mk, d)
            if mk.kind in ("line", "arrow") and math.hypot(mk.x2 - mk.x, mk.y2 - mk.y) < 0.4:
                return
            adv.push_undo()
            m.marks.append(mk)
            self.set_selection([("mark", mk)])
            adv.touch(structure=True)
        elif k in ("move", "handle", "crop"):
            adv.touch(structure=True)
            self.selection_changed.emit()
        self.update()

    def _place_default(self, mk: TableMark, d):
        """A click without dragging: one square for shapes, longest side one square for objects."""
        c = square_center(d["a"])
        mk.x, mk.y, mk.w, mk.h = c.x(), c.y(), 1.0, 1.0
        if mk.kind == "image" and d.get("src"):
            mk.image = d.get("image") or self.adv.object_image(d["src"])
            pm = QPixmap(self.adv.image_path(mk.image))
            if not pm.isNull() and pm.width() and pm.height():
                if pm.width() >= pm.height():
                    mk.h = pm.height() / pm.width()
                else:
                    mk.w = pm.width() / pm.height()

    def _items_in(self, r: QRectF):
        m = self.adv.map()
        out = [("mark", k) for k in m.marks if r.intersects(marks.bounds(k))]
        out += [("remark", x) for x in m.remarks if r.contains(QPointF(x.x, x.y))]
        out += [("template", t) for t in m.templates if r.contains(QPointF(t.x, t.y))]
        out += [("marker", k) for k in self.adv.markers if k.map == m.id and r.contains(QPointF(k.x, k.y))]
        return out

    def mouseDoubleClickEvent(self, e):
        mp = self.to_map(e.position())
        if self.tool == "polygon" and len(self.poly) >= 3:
            self.close_polygon()
            return
        if self.tool not in ("select", "tile"):
            return
        hit = self.item_at(mp)
        if hit is None and self.tool == "tile":
            m = self.adv.map()
            tile = next((x for x in m.tiles if x.rect().contains(mp)), None) if m else None
            hit = ("tile", tile) if tile else None
        if hit is None:
            return
        kind, obj = hit
        self.drag = None
        if kind == "mark" and obj.kind == "text":
            self.win.edit_table_text(obj)
        elif kind == "remark":
            self.win.edit_remark(obj)
        elif kind == "tile":
            self.win.edit_tile(obj)
        elif kind == "marker":
            self.win.set_active_marker(obj.id)

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def close_polygon(self):
        if len(self.poly) < 3:
            return
        self.adv.push_undo()
        self.adv.map_fog().paint_polygon(self.poly, reveal=True)
        self.poly = []
        self.adv.check_reveal_popups()
        self.adv.touch()

    # ================================================================ context menu
    def context_menu(self, pos):
        mp = self.to_map(pos)
        adv, m, win = self.adv, self.adv.map(), self.win
        if not m:
            return
        menu = QMenu(self)
        hit = self.item_at(mp)
        if hit and not any(o is hit[1] for _, o in self.selection):
            self.set_selection([hit])
        if hit:
            kind, obj = hit
            if kind == "mark" and obj.kind == "text":
                menu.addAction("Edit text…", lambda: win.edit_table_text(obj))
            if kind == "remark":
                menu.addAction("Edit remark…", lambda: win.edit_remark(obj))
                if obj.link:
                    menu.addAction("Follow link", lambda: adv.follow_link(obj.link))
            if kind == "marker":
                menu.addAction("Make active", lambda: win.set_active_marker(obj.id))
            if kind == "tile":
                menu.addAction(f"Edit tile {obj.name}…", lambda: win.edit_tile(obj))
            if kind == "part":
                menu.addAction("Rotate 90°", lambda: win.rotate_part(obj))
                menu.addAction("Make tile from this part", lambda: win.tile_from_part(obj))
            if kind in ("mark", "part"):
                menu.addAction("Bring to front", lambda: self.reorder(True))
                menu.addAction("Send to back", lambda: self.reorder(False))
                menu.addAction("Unlock" if obj.locked else "Lock", lambda: win.set_selection_flag("locked", not obj.locked))
            if kind == "mark":
                menu.addAction("Show on table" if obj.dm_only else "DM only",
                               lambda: win.set_selection_flag("dm_only", not obj.dm_only))
            if kind in ("mark", "remark", "template"):
                menu.addAction("Copy  (Ctrl+C)", self.copy_selection)
            if kind == "template":
                menu.addAction("Unpin template", self.delete_selection)
            else:
                menu.addAction("Delete  (Del)", self.delete_selection)
            menu.addSeparator()
        if self.clipboard:
            menu.addAction("Paste here  (Ctrl+V)", self.paste)
        if self.overlay and self.overlay.kind == "template":
            menu.addAction("Pin current template  (P)", self.pin_overlay)
        tile = next((t for t in m.tiles if t.rect().contains(mp) and t.id == adv.current_tile.get(m.id)), None) \
            or next((t for t in m.tiles if t.rect().contains(mp)), None)
        if tile:
            menu.addAction(f"Show tile {tile.name} on table", lambda: adv.go_to_tile(tile.id))
        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(pos.toPoint()))
