"""Data model: adventure -> maps -> parts and tiles, plus fog, marks and session state.

All map positions are in grid squares (floats). Square (3, 5) spans x 3..4, y 5..6,
so its center is (3.5, 5.5).
"""
from __future__ import annotations

import copy
import json
import math
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field, fields

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF, QTransform

FOG_RES = 8          # fog pixels per grid square
UNDO_LIMIT = 60


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _from_dict(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class MapPart:
    """One imported image, placed on the map by its own grid."""
    id: str
    image: str                 # file name inside the adventure's images folder
    w: int                     # image size in pixels
    h: int
    cell_px: float = 70.0      # image pixels per grid square
    ox: float = 0.0            # image pixel position of one grid intersection
    oy: float = 0.0
    gx: int = 0                # map square that intersection (ox, oy) sits on
    gy: int = 0
    crop: list | None = None   # [x, y, w, h] in image pixels, or None for the whole image
    locked: bool = False
    aligned: bool = False      # the DM has set this part's grid

    def crop_rect(self) -> QRectF:
        if self.crop:
            return QRectF(*self.crop)
        return QRectF(0, 0, self.w, self.h)

    def image_to_squares(self) -> QTransform:
        """Transform from image pixels to map squares."""
        s = 1.0 / self.cell_px
        t = QTransform()
        t.translate(self.gx - self.ox * s, self.gy - self.oy * s)
        t.scale(s, s)
        return t

    def bounds(self) -> QRectF:
        return self.image_to_squares().mapRect(self.crop_rect())


@dataclass
class Tile:
    """A table-sized window onto the map, in whole squares."""
    id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    neighbours: dict = field(default_factory=dict)   # "up"/"down"/"left"/"right" -> tile id; missing = automatic

    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.w, self.h)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


@dataclass
class Remark:
    """DM-only note pinned to the map, optionally carrying a special link."""
    id: str
    x: float
    y: float
    text: str
    popup: bool = True                 # remind the DM when the fog here is revealed
    notified: bool = False
    link: dict | None = None           # {"map": id, "tile": id, "ax": float, "ay": float}


MARK_KINDS = ("rect", "circle", "triangle", "line", "arrow", "text", "image")


@dataclass
class TableMark:
    """Text, shape or image object on the table. Drawn in list order, last on top.

    Lines and arrows run from (x, y) to (x2, y2); everything else is centred on (x, y)
    with size w x h squares, turned by rotation degrees.
    """
    id: str
    kind: str                          # one of MARK_KINDS
    x: float
    y: float
    x2: float = 0.0
    y2: float = 0.0
    r: float = 0.0                     # old circle radius, converted to w/h on load
    text: str = ""
    facing: int = 0                    # old text facing, converted to rotation on load
    w: float = 1.0
    h: float = 1.0
    rotation: float = 0.0
    fill: str = ""                     # "" = no fill; for text the plate colour
    stroke: str = "#2C2C2A"            # "" = no outline; for text the text and border colour
    opacity: float = 1.0               # fill opacity, or the whole image for objects
    text_size: float = 0.35            # text height in squares
    image: str = ""                    # file name in the adventure's images folder
    dm_only: bool = False
    locked: bool = False

    def upgrade(self):
        if self.kind == "circle" and self.r:
            self.w = self.h = 2 * self.r
            self.r = 0.0
        if self.kind == "text" and self.facing:
            self.rotation = {90: 90, 180: 180, 270: -90}.get(self.facing, 0)
            self.facing = 0
        if self.kind == "text" and not self.fill:
            self.fill = "#F4EBD6"
        return self


@dataclass
class Template:
    """Area template or range circle. Origin and direction point in squares."""
    id: str
    shape: str                         # "sphere", "cone", "line", "cube", "range"
    x: float
    y: float
    dx: float = 0.0
    dy: float = 0.0
    size_ft: int = 20


@dataclass
class Marker:
    """Party marker the DM places; shown as a ghost on the table after transitions."""
    id: str
    name: str
    map: str
    x: float
    y: float


@dataclass
class GameMap:
    id: str
    name: str
    parts: list = field(default_factory=list)
    tiles: list = field(default_factory=list)
    remarks: list = field(default_factory=list)
    marks: list = field(default_factory=list)
    templates: list = field(default_factory=list)   # pinned templates

    def bounds(self) -> QRectF:
        r = QRectF()
        for p in self.parts:
            r = r.united(p.bounds()) if not r.isNull() else p.bounds()
        return r

    def tile(self, tile_id) -> Tile | None:
        return next((t for t in self.tiles if t.id == tile_id), None)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GameMap":
        m = _from_dict(cls, d)
        m.parts = [_from_dict(MapPart, p) for p in d.get("parts", [])]
        m.tiles = [_from_dict(Tile, t) for t in d.get("tiles", [])]
        m.remarks = [_from_dict(Remark, r) for r in d.get("remarks", [])]
        m.marks = [_from_dict(TableMark, k).upgrade() for k in d.get("marks", [])]
        m.templates = [_from_dict(Template, t) for t in d.get("templates", [])]
        return m


class Fog:
    """Fog raster for one map. Alpha 255 = fogged, 0 = revealed."""

    def __init__(self, x=0, y=0, w=1, h=1, image: QImage | None = None):
        self.x, self.y, self.w, self.h = x, y, w, h
        if image is None:
            image = QImage(w * FOG_RES, h * FOG_RES, QImage.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 255))
        self.image = image

    def copy(self) -> "Fog":
        return Fog(self.x, self.y, self.w, self.h, self.image.copy())

    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.w, self.h)

    def ensure(self, bounds: QRectF):
        """Grow the raster so it covers bounds; new area starts fogged."""
        if bounds.isNull():
            return
        x0 = min(self.x, math.floor(bounds.left()))
        y0 = min(self.y, math.floor(bounds.top()))
        x1 = max(self.x + self.w, math.ceil(bounds.right()))
        y1 = max(self.y + self.h, math.ceil(bounds.bottom()))
        if (x0, y0, x1, y1) == (self.x, self.y, self.x + self.w, self.y + self.h):
            return
        img = QImage((x1 - x0) * FOG_RES, (y1 - y0) * FOG_RES, QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(0, 0, 0, 255))
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage((self.x - x0) * FOG_RES, (self.y - y0) * FOG_RES, self.image)
        p.end()
        self.x, self.y, self.w, self.h, self.image = x0, y0, x1 - x0, y1 - y0, img

    def _painter(self) -> QPainter:
        p = QPainter(self.image)
        p.setRenderHint(QPainter.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.setPen(Qt.NoPen)
        p.scale(FOG_RES, FOG_RES)
        p.translate(-self.x, -self.y)
        return p

    def paint_circle(self, cx, cy, r, reveal: bool):
        p = self._painter()
        p.setBrush(QColor(0, 0, 0, 0 if reveal else 255))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.end()

    def paint_stroke(self, a: QPointF, b: QPointF, r, reveal: bool):
        p = self._painter()
        pen = QPen(QColor(0, 0, 0, 0 if reveal else 255), 2 * r, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(a, b)
        p.end()

    def paint_polygon(self, pts, reveal: bool):
        p = self._painter()
        p.setBrush(QColor(0, 0, 0, 0 if reveal else 255))
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        p.end()

    def is_fogged(self, x, y) -> bool:
        px = int((x - self.x) * FOG_RES)
        py = int((y - self.y) * FOG_RES)
        if not (0 <= px < self.image.width() and 0 <= py < self.image.height()):
            return True
        return self.image.pixelColor(px, py).alpha() > 127


class PlayerState:
    """Everything the table shows. Live it references the model; frozen it is a copy."""

    def __init__(self, game_map, fog, tile, ghosts):
        self.map = game_map
        self.fog = fog
        self.tile = tile
        self.ghosts = ghosts      # list of (x, y) square positions

    def frozen_copy(self) -> "PlayerState":
        return PlayerState(copy.deepcopy(self.map), self.fog.copy() if self.fog else None,
                           copy.deepcopy(self.tile), list(self.ghosts))


class Adventure(QObject):
    """The open adventure plus live session state. Emits changed for any visible change."""

    changed = Signal()            # repaint
    structure_changed = Signal()  # lists in the side panel need refreshing
    notice = Signal(str, str)     # (kind, message) for the DM: kind is "info", "warn" or "remark"

    def __init__(self, folder: str):
        super().__init__()
        self.folder = folder
        self.name = os.path.basename(folder.rstrip("/\\")) or "Adventure"
        self.maps: list[GameMap] = []
        self.fog: dict[str, Fog] = {}
        self.markers: list[Marker] = []
        self.active_marker: str | None = None
        self.current_map: str | None = None
        self.current_tile: dict[str, str] = {}      # map id -> tile id on the table
        # session-only state
        self.frozen = False
        self.published: PlayerState | None = None
        self.panic = False
        self.ghosts_pending = False
        self.live_overlay = None                     # measurement shown on the table (always live)
        self.dirty = False
        self.last_saved = None
        self._undo: list = []
        self._redo: list = []
        self._last_coalesce = None
        self._last_push = 0.0

    # ---------- access ----------
    def map(self, map_id=None) -> GameMap | None:
        map_id = map_id or self.current_map
        return next((m for m in self.maps if m.id == map_id), None)

    def table_tile(self, map_id=None) -> Tile | None:
        m = self.map(map_id)
        if not m:
            return None
        return m.tile(self.current_tile.get(m.id))

    def marker(self, marker_id=None) -> Marker | None:
        marker_id = marker_id or self.active_marker
        return next((k for k in self.markers if k.id == marker_id), None)

    def map_fog(self, map_id=None) -> Fog | None:
        m = self.map(map_id)
        if not m:
            return None
        fog = self.fog.get(m.id)
        if fog is None:
            b = m.bounds()
            fog = Fog(math.floor(b.left()), math.floor(b.top()),
                      max(1, math.ceil(b.width())), max(1, math.ceil(b.height())))
            self.fog[m.id] = fog
        fog.ensure(m.bounds())
        return fog

    # ---------- change notification ----------
    def touch(self, structure=False):
        self.dirty = True
        if structure:
            self.structure_changed.emit()
        self.changed.emit()

    # ---------- undo ----------
    def _snapshot(self):
        return (json.dumps(self._state_dict()), {k: f.copy() for k, f in self.fog.items()})

    def push_undo(self, coalesce: str | None = None):
        """Remember the state for undo. Repeated pushes with the same coalesce key within
        a second (spin box steps, slider moves) count as one step."""
        now = time.monotonic()
        if coalesce and self._last_coalesce == (coalesce, ) and now - self._last_push < 1.0:
            self._last_push = now
            return
        self._last_coalesce = (coalesce, ) if coalesce else None
        self._last_push = now
        self._undo.append(self._snapshot())
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def _restore(self, snap):
        state, fog = snap
        self._load_state(json.loads(state), keep_session=True)
        self.fog = {k: f.copy() for k, f in fog.items()}
        self.touch(structure=True)

    def undo(self):
        if self._undo:
            self._redo.append(self._snapshot())
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo:
            self._undo.append(self._snapshot())
            self._restore(self._redo.pop())

    # ---------- table state ----------
    def live_state(self) -> PlayerState:
        m = self.map()
        ghosts = []
        if self.ghosts_pending and m:
            ghosts = [(k.x, k.y) for k in self.markers if k.map == m.id]
        return PlayerState(m, self.map_fog() if m else None, self.table_tile(), ghosts)

    def player_state(self) -> PlayerState:
        if self.frozen and self.published is not None:
            return self.published
        return self.live_state()

    def set_frozen(self, frozen: bool):
        if frozen and not self.frozen:
            self.published = self.live_state().frozen_copy()
        self.frozen = frozen
        if not frozen:
            self.published = None
        self.changed.emit()

    def publish(self):
        """Push all pending changes to the table and end freeze (FRZ-4)."""
        self.set_frozen(False)

    def set_panic(self, on: bool):
        self.panic = on
        self.changed.emit()

    # ---------- tiles and transitions ----------
    def go_to_tile(self, tile_id, map_id=None):
        m = self.map(map_id)
        if not m or not m.tile(tile_id):
            return
        self.current_map = m.id
        self.current_tile[m.id] = tile_id
        self.ghosts_pending = any(k.map == m.id for k in self.markers)
        active = self.marker()
        tile = m.tile(tile_id)
        if active and active.map == m.id and not tile.contains(active.x, active.y):
            self.notice.emit("warn", f"Party marker “{active.name}” is outside tile {tile.name}.")
        self.touch(structure=True)

    def follow_link(self, link: dict):
        m = self.map(link.get("map"))
        if not m or not m.tile(link.get("tile")):
            self.notice.emit("warn", "This link points to a tile that no longer exists.")
            return
        active = self.marker()
        if active:
            active.map = m.id
            active.x, active.y = link.get("ax", 0.0), link.get("ay", 0.0)
        self.go_to_tile(link["tile"], m.id)

    def confirm_ghosts(self):
        self.ghosts_pending = False
        self.changed.emit()

    def check_reveal_popups(self):
        """Remind the DM of remarks whose spot was just revealed (REM-3)."""
        m, fog = self.map(), self.map_fog()
        if not m or not fog:
            return
        for r in m.remarks:
            fogged = fog.is_fogged(r.x, r.y)
            if r.popup and not r.notified and not fogged:
                r.notified = True
                self.notice.emit("remark", r.text)
            elif fogged and r.notified:
                r.notified = False

    # ---------- files ----------
    @property
    def images_dir(self) -> str:
        return os.path.join(self.folder, "images")

    def image_path(self, name: str) -> str:
        return os.path.join(self.images_dir, name)

    def add_image(self, img: QImage, suffix=".png") -> str:
        os.makedirs(self.images_dir, exist_ok=True)
        name = new_id() + suffix
        img.save(self.image_path(name))
        return name

    def copy_image_file(self, src: str) -> str:
        os.makedirs(self.images_dir, exist_ok=True)
        name = new_id() + os.path.splitext(src)[1].lower()
        shutil.copyfile(src, self.image_path(name))
        return name

    def object_image(self, src: str) -> str:
        """Copy a library object into the adventure once and return its image name (PRM-13)."""
        os.makedirs(self.images_dir, exist_ok=True)
        base = "".join(c if c.isalnum() or c in "-_" else "_" for c in os.path.splitext(os.path.basename(src))[0])
        name = f"obj_{base}_{os.path.getsize(src)}.png"
        if not os.path.exists(self.image_path(name)):
            shutil.copyfile(src, self.image_path(name))
        return name

    def _state_dict(self) -> dict:
        return {
            "version": 1,
            "name": self.name,
            "maps": [m.to_dict() for m in self.maps],
            "markers": [asdict(k) for k in self.markers],
            "active_marker": self.active_marker,
            "current_map": self.current_map,
            "current_tile": self.current_tile,
            "fog": {k: [f.x, f.y, f.w, f.h] for k, f in self.fog.items()},
        }

    def _load_state(self, d: dict, keep_session=False):
        self.name = d.get("name", self.name)
        self.maps = [GameMap.from_dict(m) for m in d.get("maps", [])]
        self.markers = [_from_dict(Marker, k) for k in d.get("markers", [])]
        self.active_marker = d.get("active_marker")
        if not keep_session:
            self.current_map = d.get("current_map")
            self.current_tile = d.get("current_tile", {})
        if not self.map(self.current_map):
            self.current_map = self.maps[0].id if self.maps else None

    def save(self):
        os.makedirs(self.folder, exist_ok=True)
        state = self._state_dict()
        for map_id, fog in self.fog.items():
            fog.image.save(os.path.join(self.folder, f"fog_{map_id}.png"))
        tmp = os.path.join(self.folder, "adventure.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, os.path.join(self.folder, "adventure.json"))
        self.dirty = False
        self.last_saved = time.localtime()

    @classmethod
    def load(cls, folder: str) -> "Adventure":
        adv = cls(folder)
        path = os.path.join(folder, "adventure.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            adv._load_state(d)
            for map_id, (x, y, w, h) in d.get("fog", {}).items():
                img = QImage(os.path.join(folder, f"fog_{map_id}.png"))
                if not img.isNull():
                    img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
                    adv.fog[map_id] = Fog(x, y, w, h, img)
        return adv
