"""The DM window: header, grouped toolbar, map, side panel, menus, status bar and hotkeys."""
from __future__ import annotations

import glob
import math
import os
import shutil
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QGuiApplication, QIcon, QKeySequence,
                           QPainter, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

from dndmap import importer, style
from dndmap.dialogs import (FACINGS, AdventureLocationDialog, GridDialog, ImportDialog, RemarkDialog,
                            TableSetupDialog, TableTextDialog, TileDialog)
from dndmap.geometry import coverage_warnings, neighbour
from dndmap.map_view import PREP_TOOLS, MapView
from dndmap.model import Adventure, GameMap, Marker, Remark, TableMark, Tile, new_id
from dndmap.player_window import PlayerWindow, TablePreview

TOOLS = {
    # tool: (label, key, tooltip)
    "tile": ("Tile", "", "Click to add a table-sized tile, drag to move it, double-click to edit"),
    "select": ("Select", "Q", "Select, move, resize and rotate; Shift-click or drag a box for several"),
    "reveal": ("Reveal", "V", "Brush that removes fog"),
    "fogrect": ("Rect", "E", "Drag a rectangle to reveal it; hold Shift to hide it"),
    "polygon": ("Polygon", "O", "Click a room's corners to reveal it; click the first corner or double-click to finish"),
    "hide": ("Hide", "H", "Brush that adds fog back"),
    "ruler": ("Ruler", "R", "Drag from square to square"),
    "range": ("Range", "C", "Drag out a range circle"),
    "template": ("Template", "T", "Click the origin, drag the direction; shape and size in Tool options"),
    "marker": ("Party", "M", "Click to place the active party marker"),
    "note": ("DM note", "N", "Click to pin a DM-only remark"),
    "mark": ("Table mark", "K", "Shapes, text and objects shown to the players; pick them in the Mark palette"),
}

PALETTE = ["#E24B4A", "#EF9F27", "#F2E255", "#639922", "#378ADD", "#7F77DD", "#FFFFFF", "#2C2C2A"]
SHAPES = [("rect", "Rectangle"), ("circle", "Circle"), ("triangle", "Triangle"),
          ("line", "Line"), ("arrow", "Arrow"), ("text", "Text")]
KIND_NAMES = dict(SHAPES, image="Object")
ROTATION_TO_FACING = {0: 0, 90: 90, 180: 180, -180: 180, -90: 270, 270: 270}

HOTKEYS = """\
Arrow keys      Nudge the selection one square; with nothing selected,
                show the neighbouring tile on the table
Q               Select tool (Esc also returns to it)
Delete          Delete the selection
Ctrl+C / Ctrl+V Copy / paste at the mouse position
Alt (held)      Move, resize or place without snapping to the grid
Shift-click     Add to or remove from the selection
F               Freeze / unfreeze the table
Enter           Publish changes (ends freeze)
B               Panic: table black / back
G               Minis placed (hide ghost outlines)
S               Show current measurement on the table
P               Pin current template
Esc             Clear measurement, polygon or selection
[  ]            Smaller / larger fog brush
V E O H         Reveal brush, rectangle, polygon reveal, hide brush
                (Rectangle with Shift held hides)
R C T           Ruler, range circle, template
M N K           Party marker, DM note, table mark
Home            Center on the table tile
Ctrl+Z / Ctrl+Y Undo / redo
F11             Table window full screen on the projector
Right-drag or middle-drag pans, the mouse wheel zooms, right-click opens item menus."""


def _icon(kind: str) -> QIcon:
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if kind == "eye":
        p.setPen(QPen(style.INK, 1.2))
        p.drawEllipse(QRectF(1.5, 4, 11, 6))
        p.setBrush(style.INK)
        p.drawEllipse(QPointF(7, 7), 1.6, 1.6)
    elif kind == "lock":
        p.setPen(QPen(style.RULER, 1.3))
        p.drawArc(QRectF(4, 1.5, 6, 7), 0, 180 * 16)
        p.setBrush(style.RULER)
        p.drawRect(QRectF(3, 6, 8, 6.5))
    elif kind == "link":
        p.setPen(QPen(style.GOLD, 1.6))
        p.drawLine(2, 7, 11, 7)
        p.drawLine(8, 4, 11, 7)
        p.drawLine(8, 10, 11, 7)
    p.end()
    return QIcon(pm)


def _shape_icon(kind: str) -> QIcon:
    pm = QPixmap(18, 18)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(style.INK, 1.6))
    if kind == "rect":
        p.drawRect(QRectF(2, 4, 14, 10))
    elif kind == "circle":
        p.drawEllipse(QRectF(2.5, 2.5, 13, 13))
    elif kind == "triangle":
        p.drawPolygon(QPolygonF([QPointF(9, 2.5), QPointF(16, 15.5), QPointF(2, 15.5)]))
    elif kind == "line":
        p.drawLine(QPointF(2.5, 15.5), QPointF(15.5, 2.5))
    elif kind == "arrow":
        p.drawLine(QPointF(2.5, 15.5), QPointF(13, 5))
        p.setBrush(style.INK)
        p.drawPolygon(QPolygonF([QPointF(16, 2), QPointF(9, 4), QPointF(14, 9)]))
    elif kind == "text":
        f = style.note_font(15)
        p.setFont(f)
        p.drawText(QRectF(0, 0, 18, 18), Qt.AlignCenter, "T")
    p.end()
    return QIcon(pm)


def _head(text: str) -> QLabel:
    lab = QLabel("◆  " + text)
    lab.setObjectName("sideHead")
    return lab


class ColorRow(QWidget):
    """Palette swatches plus 'none' and a custom colour picker. Emits the chosen hex ('' = none)."""
    picked = Signal(str)

    def __init__(self, allow_none=True):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(2)
        self.buttons = {}
        for c in PALETTE:
            self._add(h, c, c)
        if allow_none:
            self._add(h, "", None)
        more = QToolButton(text="…", objectName="swatch")
        more.setToolTip("Custom colour")
        more.setFixedSize(19, 19)
        more.setFocusPolicy(Qt.NoFocus)
        more.clicked.connect(self._custom)
        h.addWidget(more)
        h.addStretch(1)
        self.current = None

    def _add(self, layout, value, color):
        b = QToolButton(objectName="swatch", checkable=True)
        b.setFixedSize(19, 19)
        b.setFocusPolicy(Qt.NoFocus)
        pm = QPixmap(14, 14)
        pm.fill(QColor(color) if color else QColor("white"))
        p = QPainter(pm)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawRect(0, 0, 13, 13)
        if not color:
            p.setPen(QPen(style.RULER, 1.6))
            p.drawLine(2, 2, 12, 12)
            p.drawLine(12, 2, 2, 12)
        p.end()
        b.setIcon(QIcon(pm))
        b.setIconSize(QSize(14, 14))
        b.setToolTip(color or "None")
        b.clicked.connect(lambda: self._choose(value))
        layout.addWidget(b)
        self.buttons[value] = b

    def _custom(self):
        c = QColorDialog.getColor(QColor(self.current or "#E24B4A"), self, "Colour")
        if c.isValid():
            self._choose(c.name().upper())

    def _choose(self, value):
        self.set_current(value)
        self.picked.emit(value)

    def set_current(self, value):
        self.current = value
        for v, b in self.buttons.items():
            b.setChecked(v.upper() == (value or "").upper())


class MainWindow(QMainWindow):
    def __init__(self, adv: Adventure, setup):
        super().__init__()
        self.setup = setup
        self.adv: Adventure | None = None
        self.prep_mode = False
        self._updating_panel = False
        self.pal_kind = "rect"
        self.pal_fill = "#E24B4A"
        self.pal_stroke = "#A32D2D"
        self.pal_image = ""
        self.setWindowTitle("Table Map — DM")
        self.resize(1400, 880)

        central = QWidget(objectName="central")
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._build_header())
        v.addWidget(self._build_toolbar())
        body = QHBoxLayout()
        body.setSpacing(0)
        self.map_view = MapView(self)
        body.addWidget(self.map_view, 1)
        body.addWidget(self._build_side())
        v.addLayout(body, 1)
        self.setCentralWidget(central)

        self.player = PlayerWindow(self)
        self._build_menus()
        self._build_status()
        self.map_view.cursor_moved.connect(
            lambda x, y: self.lbl_cursor.setText(f"Square {math.floor(x)}, {math.floor(y)}"))
        self.map_view.selection_changed.connect(self.refresh_selection_panel)

        self.autosave = QTimer(self, interval=3000, timeout=self._autosave)
        self.autosave.start()
        self.set_adventure(adv)
        self.set_tool("select")
        self.set_prep(not any(m.parts for m in adv.maps))
        self.set_show_grid(self.setup.show_grid)
        self.refresh_library()

    # ================================================================ building
    def _build_header(self):
        f = QFrame(objectName="header")
        h = QHBoxLayout(f)
        h.setContentsMargins(10, 5, 10, 5)
        self.lbl_title = QLabel(objectName="title")
        dash = QLabel("—")
        dash.setStyleSheet("color:#BA7517;")
        self.map_combo = QComboBox()
        self.map_combo.setMinimumWidth(160)
        self.map_combo.setFocusPolicy(Qt.NoFocus)
        self.map_combo.activated.connect(self._map_chosen)
        h.addWidget(self.lbl_title)
        h.addWidget(dash)
        h.addWidget(self.map_combo)
        h.addStretch(1)
        self.chk_grid_head = QCheckBox("Show grid")
        self.chk_grid_head.setFocusPolicy(Qt.NoFocus)
        self.chk_grid_head.setToolTip("Show the square grid over the map  [Ctrl+G]")
        self.chk_grid_head.clicked.connect(self.set_show_grid)
        h.addWidget(self.chk_grid_head)
        h.addSpacing(12)
        self.btn_prep = QToolButton(text="Prep", checkable=True)
        self.btn_live = QToolButton(text="Live", checkable=True)
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for b in (self.btn_prep, self.btn_live):
            b.setFocusPolicy(Qt.NoFocus)
            grp.addButton(b)
            h.addWidget(b)
        self.btn_prep.clicked.connect(lambda: self.set_prep(True))
        self.btn_live.clicked.connect(lambda: self.set_prep(False))
        return f

    def _group(self, caption: str, buttons: list) -> QFrame:
        g = QFrame(objectName="group")
        v = QVBoxLayout(g)
        v.setContentsMargins(6, 0, 6, 0)
        v.setSpacing(2)
        cap = QLabel(caption, objectName="cap")
        cap.setAlignment(Qt.AlignCenter)
        v.addWidget(cap)
        row = QHBoxLayout()
        row.setSpacing(3)
        for b in buttons:
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        v.addLayout(row)
        return g

    def _tool_button(self, tool: str) -> QToolButton:
        label, key, tip = TOOLS[tool]
        b = QToolButton(text=label, checkable=True)
        b.setToolTip(f"{tip}" + (f"  [{key}]" if key else ""))
        b.clicked.connect(lambda: self.set_tool(tool))
        self.tool_group.addButton(b)
        self.tool_buttons[tool] = b
        return b

    def _build_toolbar(self):
        f = QFrame(objectName="toolbar")
        h = QHBoxLayout(f)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(0)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        btn_import = QToolButton(text="Import")
        btn_import.setToolTip("Import map images or PDFs  [Ctrl+I]")
        btn_import.clicked.connect(self.import_maps)
        self.prep_group = self._group("Prep", [btn_import, self._tool_button("tile")])
        h.addWidget(self.prep_group)
        h.addWidget(self._group("Select", [self._tool_button("select")]))
        h.addWidget(self._group("Fog", [self._tool_button(t) for t in ("reveal", "fogrect", "polygon", "hide")]))
        h.addWidget(self._group("Measure", [self._tool_button(t) for t in ("ruler", "range", "template")]))
        h.addWidget(self._group("Mark", [self._tool_button(t) for t in ("marker", "note", "mark")]))
        self.btn_freeze = QToolButton(text="Freeze", checkable=True)
        self.btn_freeze.setToolTip("Table keeps its picture while you prepare changes  [F]")
        self.btn_freeze.clicked.connect(self.set_frozen)
        btn_publish = QToolButton(text="Publish")
        btn_publish.setToolTip("Push all changes to the table and end freeze  [Enter]")
        btn_publish.clicked.connect(self.publish)
        self.btn_panic = QToolButton(text="Panic", checkable=True, objectName="panic")
        self.btn_panic.setToolTip("Table goes black immediately; press again to restore  [B]")
        self.btn_panic.clicked.connect(self.set_panic)
        h.addWidget(self._group("Table", [self.btn_freeze, btn_publish, self.btn_panic]))
        h.addStretch(1)
        return f

    def _row(self, layout, label, *widgets) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(4)
        if label is not None:
            lab = QLabel(label)
            lab.setFixedWidth(58)
            hl.addWidget(lab)
        for w in widgets:
            hl.addWidget(w, 1)
        layout.addWidget(row)
        return row

    def _build_side(self):
        outer = QFrame(objectName="side")
        outer.setFixedWidth(316)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFocusPolicy(Qt.NoFocus)
        ol.addWidget(scroll)
        inner = QWidget()
        inner.setStyleSheet("background:#FFFFFF;")
        v = QVBoxLayout(inner)
        v.setContentsMargins(8, 2, 8, 8)
        v.setSpacing(4)
        scroll.setWidget(inner)

        v.addWidget(_head("On the table"))
        self.preview = TablePreview(self)
        v.addWidget(self.preview)
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("color:#5F5E5A;font-size:11px;")
        self.lbl_preview.setWordWrap(True)
        v.addWidget(self.lbl_preview)

        self._build_selection_panel(v)
        self._build_tool_options(v)
        self._build_palette(v)

        v.addWidget(_head("Tiles"))
        self.list_tiles = self._list(v, 110)
        self.list_tiles.itemClicked.connect(lambda it: self.show_tile(it.data(Qt.UserRole)))
        self.tile_buttons = self._buttons(v, [("Edit", self._edit_selected_tile),
                                              ("Delete", self._delete_selected_tile),
                                              ("Check gaps", self.check_coverage)])

        v.addWidget(_head("Party markers"))
        self.list_markers = self._list(v, 56)
        self.list_markers.itemClicked.connect(lambda it: self.set_active_marker(it.data(Qt.UserRole)))
        self._buttons(v, [("Add", self.add_marker), ("Rename", self.rename_marker),
                          ("Delete", self._delete_selected_marker)])

        v.addWidget(_head("Remarks and table marks"))
        self.list_remarks = self._list(v, 100)
        self.list_remarks.itemClicked.connect(self._remark_clicked)
        self.list_remarks.itemDoubleClicked.connect(self._remark_double_clicked)

        self.parts_head = _head("Map parts")
        v.addWidget(self.parts_head)
        self.list_parts = self._list(v, 70)
        self.list_parts.itemClicked.connect(self._part_clicked)
        v.addStretch(1)
        return outer

    def _build_selection_panel(self, v):
        self.sel_box = QWidget()
        sv = QVBoxLayout(self.sel_box)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(3)
        self.sel_head = _head("Selection")
        sv.addWidget(self.sel_head)
        self.ed_text = QLineEdit()
        self.ed_text.textEdited.connect(lambda t: self._set_mark_attr("text", t, "text"))
        self.ed_tsize = QDoubleSpinBox(minimum=0.15, maximum=6, singleStep=0.05, decimals=2, suffix=" sq")
        self.ed_tsize.valueChanged.connect(lambda val: self._set_mark_attr("text_size", val, "tsize"))
        self.ed_w = QDoubleSpinBox(minimum=0.25, maximum=200, singleStep=0.5, decimals=2, suffix=" sq")
        self.ed_h = QDoubleSpinBox(minimum=0.25, maximum=200, singleStep=0.5, decimals=2, suffix=" sq")
        self.ed_w.valueChanged.connect(lambda val: self._set_mark_attr("w", val, "w"))
        self.ed_h.valueChanged.connect(lambda val: self._set_mark_attr("h", val, "h"))
        self.ed_rot = QSpinBox(minimum=-180, maximum=180, singleStep=15, suffix="°")
        self.ed_rot.valueChanged.connect(lambda val: self._set_mark_attr("rotation", float(val), "rot"))
        self.ed_facing = QComboBox()
        for label, value in FACINGS:
            self.ed_facing.addItem(label, value)
        self.ed_facing.activated.connect(self._facing_chosen)
        self.ed_fill = ColorRow()
        self.ed_fill.picked.connect(lambda c: self._set_mark_attr("fill", c, None))
        self.ed_stroke = ColorRow()
        self.ed_stroke.picked.connect(lambda c: self._set_mark_attr("stroke", c, None))
        self.ed_opacity = QSlider(Qt.Horizontal, minimum=0, maximum=100)
        self.ed_opacity.valueChanged.connect(lambda val: self._set_mark_attr("opacity", val / 100, "opacity"))
        self.chk_dm = QCheckBox("DM only (hidden from the table)")
        self.chk_dm.clicked.connect(lambda on: self.set_selection_flag("dm_only", on))
        self.chk_lock = QCheckBox("Locked")
        self.chk_lock.clicked.connect(lambda on: self.set_selection_flag("locked", on))
        self.sel_rows = {
            "text": self._row(sv, "Text", self.ed_text),
            "tsize": self._row(sv, "Size", self.ed_tsize),
            "wh": self._row(sv, "Size", self.ed_w, self.ed_h),
            "rot": self._row(sv, "Rotation", self.ed_rot),
            "facing": self._row(sv, "Faces", self.ed_facing),
            "fill": self._row(sv, "Fill", self.ed_fill),
            "stroke": self._row(sv, "Outline", self.ed_stroke),
            "opacity": self._row(sv, "Opacity", self.ed_opacity),
            "dm": self._row(sv, None, self.chk_dm),
            "lock": self._row(sv, None, self.chk_lock),
        }
        self.sel_rows["gridhead"] = QLabel("Grid", objectName="cap")
        sv.addWidget(self.sel_rows["gridhead"])
        self.lbl_grid_state = QLabel()
        self.lbl_grid_state.setWordWrap(True)
        self.sel_rows["gridstate"] = self.lbl_grid_state
        sv.addWidget(self.lbl_grid_state)
        self.btn_mark = QPushButton("Mark squares on the map", checkable=True)
        self.btn_mark.setFocusPolicy(Qt.NoFocus)
        self.btn_mark.clicked.connect(self._mark_squares)
        self.sel_rows["mark"] = self._row(sv, None, self.btn_mark)
        self.chk_grid_part = QCheckBox("Show grid")
        self.chk_grid_part.setFocusPolicy(Qt.NoFocus)
        self.chk_grid_part.clicked.connect(self.set_show_grid)
        self.sel_rows["gridshow"] = self._row(sv, None, self.chk_grid_part)
        self.ed_cell = QDoubleSpinBox(minimum=5, maximum=2000, singleStep=0.5, decimals=2, suffix=" px")
        self.ed_cell.valueChanged.connect(lambda val: self._set_part_grid("cell_px", val))
        self.ed_ox = QDoubleSpinBox(minimum=-100000, maximum=100000, singleStep=1, decimals=1, suffix=" px")
        self.ed_oy = QDoubleSpinBox(minimum=-100000, maximum=100000, singleStep=1, decimals=1, suffix=" px")
        self.ed_ox.valueChanged.connect(lambda val: self._set_part_grid("ox", val))
        self.ed_oy.valueChanged.connect(lambda val: self._set_part_grid("oy", val))
        self.sel_rows["cell"] = self._row(sv, "Square", self.ed_cell)
        self.sel_rows["offset"] = self._row(sv, "Offset", self.ed_ox, self.ed_oy)
        for w in (self.ed_cell, self.ed_ox, self.ed_oy):
            w.setFocusPolicy(Qt.ClickFocus)
            w.setMinimumWidth(60)
            w.setMaximumWidth(108)
        self.sel_rows["parthead"] = QLabel("Part", objectName="cap")
        sv.addWidget(self.sel_rows["parthead"])
        self.sel_rows["part"] = self._buttons(sv, [("Reset crop", self._reset_crop),
                                                   ("Rotate 90°", self._rotate_selected_part),
                                                   ("Make tile", self._tile_from_selected_part)])
        self.sel_rows["order"] = self._buttons(sv, [("To front", lambda: self.map_view.reorder(True)),
                                                    ("To back", lambda: self.map_view.reorder(False))])
        self.sel_rows["edit"] = self._buttons(sv, [("Edit…", self._edit_selection),
                                                   ("Delete", lambda: self.map_view.delete_selection())])
        self.lbl_sel_hint = QLabel()
        self.lbl_sel_hint.setWordWrap(True)
        self.lbl_sel_hint.setStyleSheet("color:#5F5E5A;font-size:11px;")
        sv.addWidget(self.lbl_sel_hint)
        for w in (self.ed_text, self.ed_tsize, self.ed_w, self.ed_h, self.ed_rot, self.ed_facing, self.ed_opacity):
            w.setFocusPolicy(Qt.ClickFocus)
        v.addWidget(self.sel_box)

    def _build_tool_options(self, v):
        self.opts_head = _head("Tool options")
        v.addWidget(self.opts_head)
        self.opt_brush = QDoubleSpinBox(minimum=0.5, maximum=20, singleStep=0.5, value=1.5, suffix=" sq radius")
        self.opt_shape = QComboBox()
        for label, value in (("Sphere", "sphere"), ("Cone", "cone"), ("Line", "line"), ("Cube", "cube")):
            self.opt_shape.addItem(label, value)
        self.opt_size = QSpinBox(minimum=5, maximum=500, singleStep=5, value=20, suffix=" ft")
        self.opt_size.valueChanged.connect(self._template_size_changed)
        self.opt_shape.currentIndexChanged.connect(self._template_shape_changed)
        self.opt_rule = QComboBox()
        self.opt_rule.addItem("Diagonals 5 ft (5e)", "5e")
        self.opt_rule.addItem("Diagonals 5-10-5", "5-10-5")
        self.opt_rule.setCurrentIndex(max(0, self.opt_rule.findData(self.setup.rule)))
        self.opt_rule.currentIndexChanged.connect(self._rule_changed)
        self.chk_table = QCheckBox("Show on table  [S]")
        self.chk_table.toggled.connect(lambda on: self.map_view.set_show_on_table(on))
        self.btn_pin = QPushButton("Pin template  [P]")
        self.btn_pin.clicked.connect(self.pin_template)
        self.btn_clear = QPushButton("Clear  [Esc]")
        self.btn_clear.clicked.connect(self.clear_measure)
        self.lbl_tool_hint = QLabel()
        self.lbl_tool_hint.setWordWrap(True)
        self.lbl_tool_hint.setStyleSheet("color:#5F5E5A;font-size:11px;")
        self.options = {
            "brush": self._row(v, "Brush", self.opt_brush),
            "shape": self._row(v, "Shape", self.opt_shape),
            "size": self._row(v, "Size", self.opt_size),
            "rule": self._row(v, None, self.opt_rule),
        }
        for key, w in (("table", self.chk_table), ("pin", self.btn_pin), ("clear", self.btn_clear),
                       ("hint", self.lbl_tool_hint)):
            v.addWidget(w)
            self.options[key] = w
        for w in (self.opt_brush, self.opt_shape, self.opt_size, self.opt_rule, self.chk_table,
                  self.btn_pin, self.btn_clear):
            w.setFocusPolicy(Qt.ClickFocus)

    def _build_palette(self, v):
        self.pal_box = QWidget()
        pv = QVBoxLayout(self.pal_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(3)
        pv.addWidget(_head("Mark palette"))
        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(2)
        self.pal_group = QButtonGroup(self)
        self.pal_group.setExclusive(True)
        self.pal_buttons = {}
        for kind, label in SHAPES:
            b = QToolButton(checkable=True)
            b.setIcon(_shape_icon(kind))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(label)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda checked=False, k=kind: self._palette_kind(k))
            self.pal_group.addButton(b)
            self.pal_buttons[kind] = b
            rh.addWidget(b)
        rh.addStretch(1)
        pv.addWidget(row)
        self.pal_fill_row = ColorRow()
        self.pal_fill_row.picked.connect(lambda c: setattr(self, "pal_fill", c))
        self.pal_fill_row.set_current(self.pal_fill)
        self.pal_stroke_row = ColorRow()
        self.pal_stroke_row.picked.connect(lambda c: setattr(self, "pal_stroke", c))
        self.pal_stroke_row.set_current(self.pal_stroke)
        self.pal_opacity = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=35)
        self.pal_tsize = QDoubleSpinBox(minimum=0.15, maximum=6, singleStep=0.05, decimals=2, value=0.35, suffix=" sq")
        self.pal_dm = QCheckBox("Place as DM only")
        self._row(pv, "Fill", self.pal_fill_row)
        self._row(pv, "Outline", self.pal_stroke_row)
        self._row(pv, "Opacity", self.pal_opacity)
        self._row(pv, "Text size", self.pal_tsize)
        self._row(pv, None, self.pal_dm)
        hint = QLabel("Drag to draw a shape, click for one square. Alt: no snapping.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5F5E5A;font-size:11px;")
        pv.addWidget(hint)
        pv.addWidget(_head("Objects"))
        self.list_objects = QListWidget()
        self.list_objects.setViewMode(QListView.IconMode)
        self.list_objects.setIconSize(QSize(40, 40))
        self.list_objects.setGridSize(QSize(54, 62))
        self.list_objects.setResizeMode(QListView.Adjust)
        self.list_objects.setMovement(QListView.Static)
        self.list_objects.setMinimumHeight(140)
        self.list_objects.setFocusPolicy(Qt.NoFocus)
        self.list_objects.itemClicked.connect(self._object_chosen)
        pv.addWidget(self.list_objects)
        self._buttons(pv, [("Add PNG…", self.add_objects), ("Library folder…", self.choose_library)])
        for w in (self.pal_opacity, self.pal_tsize, self.pal_dm):
            w.setFocusPolicy(Qt.ClickFocus)
        self.pal_buttons["rect"].setChecked(True)
        v.addWidget(self.pal_box)

    def _list(self, layout, height) -> QListWidget:
        lw = QListWidget()
        lw.setMinimumHeight(height)
        lw.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(lw)
        return lw

    def _buttons(self, layout, specs) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(3)
        for label, fn in specs:
            b = QPushButton(label)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            h.addWidget(b)
        layout.addWidget(row)
        return row

    def _action(self, menu, text, fn, key=None, checkable=False) -> QAction:
        a = QAction(text, self)
        if key:
            a.setShortcut(QKeySequence(key))
        a.setCheckable(checkable)
        a.triggered.connect(fn)
        menu.addAction(a)
        self.addAction(a)
        return a

    def _build_menus(self):
        mb = self.menuBar()
        m = mb.addMenu("File")
        self._action(m, "New adventure…", self.new_adventure, "Ctrl+N")
        self._action(m, "Open adventure…", self.open_adventure, "Ctrl+O")
        self._action(m, "Save", self.save, "Ctrl+S")
        self._action(m, "Save adventure as…", self.save_adventure_as, "Ctrl+Shift+S")
        self._action(m, "Show adventure folder", self.show_folder)
        m.addSeparator()
        self._action(m, "Import map…", self.import_maps, "Ctrl+I")
        m.addSeparator()
        self._action(m, "Quit", self.close, "Ctrl+Q")

        m = mb.addMenu("Edit")
        self._action(m, "Undo", self.undo, "Ctrl+Z")
        self._action(m, "Redo", self.redo, "Ctrl+Y")
        m.addSeparator()
        self._action(m, "Copy", lambda: self.map_view.copy_selection(), "Ctrl+C")
        self._action(m, "Paste", lambda: self.map_view.paste(), "Ctrl+V")
        self._action(m, "Delete", lambda: self.map_view.delete_selection(), "Del")
        self._action(m, "Bring to front", lambda: self.map_view.reorder(True), "Ctrl+]")
        self._action(m, "Send to back", lambda: self.map_view.reorder(False), "Ctrl+[")
        self._action(m, "Clear / back to select tool", self.escape, "Esc")
        m.addSeparator()
        for tool, (label, key, _) in TOOLS.items():
            if key:
                self._action(m, f"{label} tool", lambda checked=False, t=tool: self.set_tool(t), key)
        self._action(m, "Smaller brush", lambda: self.opt_brush.stepDown(), "[")
        self._action(m, "Larger brush", lambda: self.opt_brush.stepUp(), "]")

        m = mb.addMenu("Map")
        self._action(m, "New empty map", self.new_map)
        self._action(m, "Rename map…", self.rename_map)
        self._action(m, "Delete map", self.delete_map)
        m.addSeparator()
        self.act_grid = self._action(m, "Show grid", self.set_show_grid, "Ctrl+G", checkable=True)
        self._action(m, "Fit whole map", self.fit_map, "Ctrl+0")
        self._action(m, "Center on table tile", self.center_on_table_tile, "Home")

        m = mb.addMenu("Tiles")
        self.nav_actions = {}
        for d, key in (("up", "Up"), ("down", "Down"), ("left", "Left"), ("right", "Right")):
            self.nav_actions[d] = self._action(m, f"Show tile {d} / nudge selection", lambda checked=False, d=d: self.go(d), key)
        m.addSeparator()
        self._action(m, "Follow special link…", self.follow_link_menu, "L")
        self._action(m, "Check gaps and coverage", self.check_coverage)

        m = mb.addMenu("Table")
        self.act_freeze = self._action(m, "Freeze", lambda: self.set_frozen(not self.adv.frozen), "F")
        self.act_publish = self._action(m, "Publish", self.publish, "Return")
        self.addAction(QAction(self, shortcut=QKeySequence("Enter"), triggered=self.publish))
        self.act_panic = self._action(m, "Panic (black table)", lambda: self.set_panic(not self.adv.panic), "B")
        self._action(m, "Minis placed (hide ghosts)", self.confirm_ghosts, "G")
        self._action(m, "Show measurement on table", lambda: self.chk_table.toggle(), "S")
        self._action(m, "Pin current template", self.pin_template, "P")
        m.addSeparator()
        self._action(m, "Table window full screen on projector", self.toggle_player_fullscreen, "F11")
        self._action(m, "Table setup…", self.table_setup)

        m = mb.addMenu("Help")
        self._action(m, "Hotkeys", lambda: QMessageBox.information(self, "Hotkeys", HOTKEYS))

    def _build_status(self):
        sb = self.statusBar()
        self.lbl_mode = QLabel()
        self.lbl_tile = QLabel()
        self.lbl_scale = QLabel()
        self.lbl_cursor = QLabel()
        self.lbl_warn = QLabel(objectName="warn")
        self.btn_ghost = QPushButton("Minis placed  [G]")
        self.btn_ghost.setFocusPolicy(Qt.NoFocus)
        self.btn_ghost.clicked.connect(self.confirm_ghosts)
        self.lbl_saved = QLabel()
        for w in (self.lbl_mode, self.lbl_tile, self.lbl_scale, self.lbl_cursor, self.lbl_warn, self.btn_ghost):
            sb.addWidget(w)
        sb.addPermanentWidget(self.lbl_saved)
        self._warn_timer = QTimer(self, singleShot=True, timeout=lambda: self.lbl_warn.setText(""))

    def app_modifiers(self):
        return QGuiApplication.keyboardModifiers()

    # ================================================================ adventure
    def set_adventure(self, adv: Adventure):
        if self.adv is not None:
            for sig in (self.adv.changed, self.adv.structure_changed, self.adv.notice):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        self.adv = adv
        adv.changed.connect(self._on_changed)
        adv.structure_changed.connect(self.refresh_lists)
        adv.notice.connect(self._on_notice)
        self.map_view.overlay = None
        self.map_view.selection = []
        self.setup.last_folder = adv.folder
        self.setup.save()
        self.btn_freeze.setChecked(False)
        self.btn_panic.setChecked(False)
        self.lbl_title.setToolTip(adv.folder)
        self.refresh_lists()
        self._on_changed()
        QTimer.singleShot(0, self.center_on_table_tile)

    def _autosave(self):
        if self.adv.dirty:
            self.save()

    def save(self):
        try:
            self.adv.save()
            if self.adv.last_saved:
                self.lbl_saved.setText("Saved " + time.strftime("%H:%M", self.adv.last_saved))
            self.lbl_saved.setToolTip(self.adv.folder)
        except OSError as e:
            self.lbl_saved.setText("Save failed")
            self.warn(f"Could not save: {e}")

    def closeEvent(self, e):
        self.save()
        self.player.close()
        e.accept()

    def _parent_folder(self) -> str:
        return os.path.dirname(self.adv.folder.rstrip("/\\"))

    def new_adventure(self):
        dlg = AdventureLocationDialog(self, "New adventure", "New adventure", self._parent_folder())
        if not dlg.exec() or not dlg.name.text().strip():
            return
        path = dlg.path()
        if os.path.exists(os.path.join(path, "adventure.json")):
            if QMessageBox.question(self, "New adventure", "There already is an adventure in this folder. "
                                                           "Open it instead?") != QMessageBox.Yes:
                return
            self.save()
            self.set_adventure(Adventure.load(path))
            return
        self.save()
        adv = Adventure.load(path)
        adv.name = dlg.name.text().strip()
        adv.save()
        self.set_adventure(adv)
        self.set_prep(True)

    def open_adventure(self):
        folder = QFileDialog.getExistingDirectory(self, "Open adventure folder", self._parent_folder())
        if not folder:
            return
        if not os.path.exists(os.path.join(folder, "adventure.json")):
            if QMessageBox.question(self, "Open adventure", "This folder has no adventure yet. "
                                                            "Start a new adventure here?") != QMessageBox.Yes:
                return
        self.save()
        self.set_adventure(Adventure.load(folder))

    def save_adventure_as(self):
        dlg = AdventureLocationDialog(self, "Save adventure as", self.adv.name + " copy", self._parent_folder())
        if not dlg.exec() or not dlg.name.text().strip():
            return
        path = dlg.path()
        if os.path.exists(path) and os.listdir(path):
            QMessageBox.warning(self, "Save adventure as", "That folder already exists and is not empty. "
                                                           "Choose another name or location.")
            return
        self.save()
        try:
            shutil.copytree(self.adv.folder, path, dirs_exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Save adventure as", f"Could not copy the adventure: {e}")
            return
        adv = Adventure.load(path)
        adv.name = dlg.name.text().strip()
        adv.save()
        self.set_adventure(adv)
        self.statusBar().showMessage(f"Saved as {path}", 6000)

    def show_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.adv.folder))

    # ================================================================ refresh
    def _on_changed(self):
        self.map_view.update()
        self.player.update()
        self.preview.update()
        self._update_status()

    def refresh_lists(self):
        adv, m = self.adv, self.adv.map()
        self.lbl_title.setText(adv.name)
        self.map_combo.blockSignals(True)
        self.map_combo.clear()
        for gm in adv.maps:
            self.map_combo.addItem(gm.name, gm.id)
        self.map_combo.setCurrentIndex(max(0, self.map_combo.findData(adv.current_map)))
        self.map_combo.blockSignals(False)

        cur = adv.current_tile.get(m.id) if m else None
        self.list_tiles.clear()
        for t in (m.tiles if m else []):
            it = QListWidgetItem(f"{t.name}" + ("   ← on table" if t.id == cur else ""))
            it.setData(Qt.UserRole, t.id)
            if t.id == cur:
                it.setBackground(style.PARCHMENT_HL)
            self.list_tiles.addItem(it)

        self.list_markers.clear()
        for k in adv.markers:
            mapname = adv.map(k.map).name if adv.map(k.map) else "?"
            it = QListWidgetItem(f"{k.name}  ({mapname})" + ("  ← active" if k.id == adv.active_marker else ""))
            it.setData(Qt.UserRole, k.id)
            self.list_markers.addItem(it)

        self.list_remarks.clear()
        for r in (m.remarks if m else []):
            it = QListWidgetItem(_icon("link" if r.link else "lock"), r.text)
            it.setData(Qt.UserRole, ("remark", r.id))
            it.setToolTip("DM only" + (" · special link" if r.link else ""))
            self.list_remarks.addItem(it)
        for k in (m.marks if m else []):
            label = k.text if k.kind == "text" else KIND_NAMES.get(k.kind, k.kind)
            it = QListWidgetItem(_icon("lock" if k.dm_only else "eye"), label + ("  (DM only)" if k.dm_only else ""))
            it.setData(Qt.UserRole, ("mark", k.id))
            it.setToolTip("DM only" if k.dm_only else "Shown on the table")
            self.list_remarks.addItem(it)

        self.list_parts.clear()
        for i, p in enumerate(m.parts if m else []):
            b = p.bounds()
            it = QListWidgetItem(f"Part {i + 1}  ·  {b.width():.0f} × {b.height():.0f} sq"
                                 + ("  (locked)" if p.locked else ""))
            it.setData(Qt.UserRole, p.id)
            self.list_parts.addItem(it)
        self.map_view.validate_selection()
        self.refresh_selection_panel()
        self._update_status()

    def _update_status(self):
        adv = self.adv
        if adv.panic:
            text, name = "  PANIC — table is black  ", "modePanic"
        elif adv.frozen:
            text, name = "  FROZEN — Enter publishes  ", "modeFrozen"
        else:
            text, name = "● Live", "modeLive"
        if self.lbl_mode.objectName() != name:
            self.lbl_mode.setObjectName(name)
            self.lbl_mode.style().unpolish(self.lbl_mode)
            self.lbl_mode.style().polish(self.lbl_mode)
        self.lbl_mode.setText(text)
        t = adv.table_tile()
        self.lbl_tile.setText(f"Tile {t.name} · {t.w} × {t.h} sq" if t else "No tile on the table")
        tw, th = self.setup.tile_size()
        self.lbl_scale.setText(f"5 ft = {self.setup.square_mm:g} mm · table {tw} × {th} sq")
        self.btn_ghost.setVisible(adv.ghosts_pending)
        self.btn_freeze.setChecked(adv.frozen)
        self.btn_panic.setChecked(adv.panic)
        if adv.frozen:
            self.lbl_preview.setText("Preview after publishing. The table still shows the frozen picture.")
        elif t:
            self.lbl_preview.setText(f"Tile {t.name} · live" + (" · ruler shown" if adv.live_overlay else ""))
        else:
            self.lbl_preview.setText("Add tiles in Prep mode, then pick one to show it on the table.")

    def warn(self, text: str):
        self.lbl_warn.setText(text)
        self._warn_timer.start(10000)

    def _on_notice(self, kind: str, text: str):
        if kind == "remark":
            self.map_view.show_toast("Remark:  " + text)
        elif kind == "warn":
            self.warn(text)
            self.map_view.show_toast(text, 5000)
        else:
            self.statusBar().showMessage(text, 5000)

    # ================================================================ selection panel
    def refresh_selection_panel(self):
        sel = self.map_view.selection
        self.sel_box.setVisible(bool(sel))
        if not sel:
            return
        self._updating_panel = True
        kinds = {k for k, _ in sel}
        show = set()
        hint = ""
        if kinds == {"mark"}:
            ms = [o for _, o in sel]
            show |= {"dm", "lock", "order", "edit"}
            if all(o.kind != "image" for o in ms):
                show |= {"stroke"}
                if all(o.kind not in ("line", "arrow") for o in ms):
                    show |= {"fill"}
            show.add("opacity")
            if len(ms) == 1:
                k = ms[0]
                head = KIND_NAMES.get(k.kind, k.kind)
                if k.kind == "text":
                    show |= {"text", "tsize", "rot", "facing"}
                    self.ed_text.setText(k.text)
                    self.ed_tsize.setValue(k.text_size)
                    self.ed_facing.setCurrentIndex(max(0, self.ed_facing.findData(
                        ROTATION_TO_FACING.get(round(k.rotation), -1))))
                elif k.kind not in ("line", "arrow"):
                    show |= {"wh", "rot"}
                    self.ed_w.setValue(k.w)
                    self.ed_h.setValue(k.h)
                if "rot" in show:
                    self.ed_rot.setValue(round(k.rotation))
            else:
                head = f"{len(ms)} table marks"
            first = ms[0]
            self.ed_fill.set_current(first.fill)
            self.ed_stroke.set_current(first.stroke)
            self.ed_opacity.setValue(round(first.opacity * 100))
            self.chk_dm.setChecked(all(o.dm_only for o in ms))
            self.chk_lock.setChecked(all(o.locked for o in ms))
        elif kinds == {"part"} and len(sel) == 1:
            part = sel[0][1]
            idx = next((i for i, p in enumerate(self.adv.map().parts) if p is part), 0)
            head = f"Map part {idx + 1}"
            show |= {"lock", "order", "gridhead", "gridstate", "mark", "gridshow", "cell", "offset",
                     "parthead", "part", "edit"}
            self.chk_lock.setChecked(part.locked)
            self.ed_cell.setValue(part.cell_px)
            self.ed_ox.setValue(part.ox)
            self.ed_oy.setValue(part.oy)
            self.btn_mark.setChecked(self.map_view.grid_mark)
            b = part.bounds()
            if self.map_view.grid_mark:
                self.lbl_grid_state.setStyleSheet("color:#185FA5;")
                self.lbl_grid_state.setText("Now drag over a block of whole squares on the map, e.g. 4 × 4, "
                                            "then enter how many squares it covers.")
            elif not part.aligned:
                self.lbl_grid_state.setStyleSheet("color:#A32D2D;")
                self.lbl_grid_state.setText("The grid of this part is not set yet. Press the button below and "
                                            "drag over a few squares, or type the square size in pixels.")
            else:
                self.lbl_grid_state.setStyleSheet("color:#3B6D11;")
                self.lbl_grid_state.setText(f"Grid set · this part is {b.width():.0f} × {b.height():.0f} "
                                            f"squares. Check that the gold lines sit on the map's lines.")
            hint = "Drag the gold borders to crop, drag inside the part to move it."
        else:
            names = {"remark": "DM remark", "template": "Pinned template", "marker": "Party marker",
                     "tile": "Tile", "part": "Map part", "mark": "Table mark"}
            head = names[sel[0][0]] if len(sel) == 1 else f"{len(sel)} items"
            show |= {"edit"}
            if "mark" in kinds or "part" in kinds:
                show |= {"lock", "order"}
                self.chk_lock.setChecked(all(getattr(o, "locked", False) for k, o in sel if k in ("mark", "part")))
        self.sel_head.setText("◆  Selection · " + head)
        for key, w in self.sel_rows.items():
            w.setVisible(key in show)
        self.lbl_sel_hint.setText(hint)
        self.lbl_sel_hint.setVisible(bool(hint))
        self._updating_panel = False

    def _selected_marks(self):
        return [o for k, o in self.map_view.selection if k == "mark"]

    def _set_mark_attr(self, attr, value, coalesce):
        if self._updating_panel:
            return
        ms = [o for o in self._selected_marks() if not o.locked or attr in ("dm_only",)]
        if not ms:
            return
        self.adv.push_undo(coalesce)
        for o in ms:
            if attr in ("w", "h", "text", "text_size") and len(ms) > 1:
                continue
            setattr(o, attr, value)
        self.adv.touch(structure=attr == "text")

    def _facing_chosen(self):
        rot = {0: 0.0, 90: 90.0, 180: 180.0, 270: -90.0}[self.ed_facing.currentData()]
        self._set_mark_attr("rotation", rot, None)
        self.refresh_selection_panel()

    def set_selection_flag(self, attr, value):
        items = [o for k, o in self.map_view.selection
                 if (k == "mark") or (k == "part" and attr == "locked")]
        if not items:
            return
        self.adv.push_undo()
        for o in items:
            setattr(o, attr, bool(value))
        self.adv.touch(structure=True)

    def _edit_selection(self):
        sel = self.map_view.selection
        if len(sel) != 1:
            return
        kind, o = sel[0]
        if kind == "mark" and o.kind == "text":
            self.edit_table_text(o)
        elif kind == "remark":
            self.edit_remark(o)
        elif kind == "tile":
            self.edit_tile(o)
        elif kind == "marker":
            self.rename_marker(o)

    # ================================================================ modes and tools
    def set_prep(self, on: bool):
        self.prep_mode = on
        self.btn_prep.setChecked(on)
        self.btn_live.setChecked(not on)
        self.prep_group.setVisible(on)
        for w in (self.parts_head, self.list_parts, self.tile_buttons):
            w.setVisible(on)
        if not on:
            if self.map_view.tool in PREP_TOOLS:
                self.set_tool("select")
            self.map_view.set_selection([(k, o) for k, o in self.map_view.selection if k not in ("part", "tile")])
        self.map_view.update()

    def set_tool(self, tool: str):
        if tool in PREP_TOOLS and not self.prep_mode:
            self.set_prep(True)
        self.map_view.set_tool(tool)
        b = self.tool_buttons.get(tool)
        if b:
            b.setChecked(True)
        show = {
            "brush": tool in ("reveal", "hide"),
            "shape": tool == "template",
            "size": tool == "template",
            "rule": tool in ("ruler",),
            "table": tool in ("ruler", "range", "template"),
            "pin": tool in ("template", "range"),
            "clear": tool in ("ruler", "range", "template", "polygon"),
            "hint": tool in ("fogrect", "polygon", "select"),
        }
        self.lbl_tool_hint.setText({
            "fogrect": "Drag a rectangle to reveal it. Hold Shift while releasing to hide it.",
            "polygon": "Click the corners; click the first corner again or double-click to finish.",
            "select": "Click to select, drag to move. Shift-click or drag a box for several. Alt: no snapping.",
        }.get(tool, ""))
        for key, w in self.options.items():
            w.setVisible(show.get(key, False))
        self.opts_head.setVisible(any(show.values()))
        self.pal_box.setVisible(tool == "mark")

    def escape(self):
        if not self.map_view.clear():
            self.set_tool("select")

    def brush_size(self) -> float:
        return self.opt_brush.value()

    def template_shape(self) -> str:
        return self.opt_shape.currentData()

    def template_size(self) -> int:
        return self.opt_size.value()

    def _template_size_changed(self, value):
        o = self.map_view.overlay
        if o and o.kind == "template" and o.template.shape != "range":
            o.template.size_ft = value
            self.map_view.sync_table_overlay()

    def _template_shape_changed(self):
        o = self.map_view.overlay
        if o and o.kind == "template" and o.template.shape != "range":
            o.template.shape = self.template_shape()
            self.map_view.sync_table_overlay()

    def _rule_changed(self):
        self.setup.rule = self.opt_rule.currentData()
        self.setup.save()
        self._on_changed()

    def set_show_grid(self, on):
        """One switch for the grid overlay: header checkbox, part panel checkbox and Map menu stay in sync."""
        on = bool(on)
        self.map_view.show_grid = on
        for w in (self.chk_grid_head, self.chk_grid_part, self.act_grid):
            w.blockSignals(True)
            w.setChecked(on)
            w.blockSignals(False)
        self.setup.show_grid = on
        self.setup.save()
        self.map_view.update()

    def clear_measure(self):
        self.map_view.poly = []
        self.map_view.set_overlay(None)

    def pin_template(self):
        if not self.map_view.pin_overlay():
            self.statusBar().showMessage("Place a template or range circle first, then pin it.", 4000)

    # ================================================================ palette and objects
    def _palette_kind(self, kind):
        self.pal_kind = kind
        self.list_objects.clearSelection()

    def palette_props(self) -> dict:
        return {"kind": self.pal_kind, "fill": self.pal_fill, "stroke": self.pal_stroke,
                "opacity": self.pal_opacity.value() / 100, "dm_only": self.pal_dm.isChecked(),
                "image_src": self.pal_image if self.pal_kind == "image" else ""}

    def _object_chosen(self, item):
        self.pal_kind = "image"
        self.pal_image = item.data(Qt.UserRole)
        self.pal_group.setExclusive(False)
        for b in self.pal_buttons.values():
            b.setChecked(False)
        self.pal_group.setExclusive(True)

    def refresh_library(self):
        self.list_objects.clear()
        folder = self.setup.library_folder
        for path in sorted(glob.glob(os.path.join(folder, "*.png"))):
            pm = QPixmap(path)
            if pm.isNull():
                continue
            it = QListWidgetItem(QIcon(pm.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)),
                                 os.path.splitext(os.path.basename(path))[0][:9])
            it.setData(Qt.UserRole, path)
            it.setToolTip(path)
            self.list_objects.addItem(it)

    def add_objects(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add PNG objects to the library", "", "PNG images (*.png)")
        if not paths:
            return
        os.makedirs(self.setup.library_folder, exist_ok=True)
        for p in paths:
            dest = os.path.join(self.setup.library_folder, os.path.basename(p))
            if os.path.abspath(p) != os.path.abspath(dest):
                shutil.copyfile(p, dest)
        self.refresh_library()

    def choose_library(self):
        folder = QFileDialog.getExistingDirectory(self, "Object library folder", self.setup.library_folder)
        if folder:
            self.setup.library_folder = folder
            self.setup.save()
            self.refresh_library()

    # ================================================================ table control
    def set_frozen(self, on: bool):
        self.adv.set_frozen(bool(on))
        self._update_status()

    def publish(self):
        self.adv.publish()
        self._update_status()

    def set_panic(self, on: bool):
        self.adv.set_panic(bool(on))
        self._update_status()

    def confirm_ghosts(self):
        self.adv.confirm_ghosts()
        self._update_status()

    def toggle_player_fullscreen(self):
        if self.player.isFullScreen():
            self.player.show_on_projector(False)
        elif not self.player.show_on_projector(True):
            self.warn("No second screen found. The table window stays a normal window.")

    def show_player(self):
        if not self.player.show_on_projector(True):
            self.player.show()
            self.player.raise_()

    def handle_table_key(self, e):
        """Keys pressed while the table window has focus."""
        mapping = {Qt.Key_Up: self.nav_actions["up"], Qt.Key_Down: self.nav_actions["down"],
                   Qt.Key_Left: self.nav_actions["left"], Qt.Key_Right: self.nav_actions["right"],
                   Qt.Key_F: self.act_freeze, Qt.Key_B: self.act_panic,
                   Qt.Key_Return: self.act_publish, Qt.Key_Enter: self.act_publish}
        if e.key() in mapping:
            mapping[e.key()].trigger()
        elif e.key() == Qt.Key_G:
            self.confirm_ghosts()
        elif e.key() == Qt.Key_Escape and self.player.isFullScreen():
            self.player.show_on_projector(False)

    def table_setup(self):
        dlg = TableSetupDialog(self, self.setup)
        if dlg.exec():
            dlg.apply()
            self.opt_rule.setCurrentIndex(max(0, self.opt_rule.findData(self.setup.rule)))
            if dlg.resize_tiles.isChecked():
                self.adv.push_undo()
                tw, th = self.setup.tile_size()
                for m in self.adv.maps:
                    for t in m.tiles:
                        t.w, t.h = tw, th
                self.adv.touch(structure=True)
            if self.player.isFullScreen():
                self.player.show_on_projector(True)
            self._on_changed()

    # ================================================================ tiles
    def show_tile(self, tile_id):
        self.adv.go_to_tile(tile_id)
        self.center_on_table_tile()

    def go(self, direction: str):
        """Arrow keys: nudge the selection if there is one (SEL-9), otherwise switch tiles."""
        if self.map_view.selection:
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[direction]
            if self.map_view.nudge(dx, dy):
                return
            self.statusBar().showMessage("The selection is locked. Esc clears it so the arrows switch tiles.", 4000)
            return
        m, cur = self.adv.map(), self.adv.table_tile()
        if not m or not m.tiles:
            self.statusBar().showMessage("This map has no tiles yet. Add some with the Tile tool in Prep mode.", 4000)
            return
        if cur is None:
            self.show_tile(m.tiles[0].id)
            return
        n = neighbour(m.tiles, cur, direction)
        if n is None:
            self.statusBar().showMessage(f"No tile {direction} of {cur.name}.", 3000)
            return
        self.show_tile(n.id)

    def center_on_table_tile(self):
        t = self.adv.table_tile()
        if t:
            self.map_view.center_on(t.rect(), margin=2)
        else:
            self.fit_map()

    def fit_map(self):
        m = self.adv.map()
        if m and not m.bounds().isNull():
            self.map_view.center_on(m.bounds())

    def next_tile_name(self, m: GameMap) -> str:
        names = {t.name for t in m.tiles}
        i = len(m.tiles) + 1
        while f"T{i}" in names:
            i += 1
        return f"T{i}"

    def edit_tile(self, tile: Tile):
        m = self.adv.map()
        dlg = TileDialog(self, m, tile)
        if dlg.exec():
            name, neighbours = dlg.values()
            self.adv.push_undo()
            tile.name = name or tile.name
            tile.neighbours = neighbours
            self.adv.touch(structure=True)

    def _selected(self, lw: QListWidget):
        it = lw.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _edit_selected_tile(self):
        m = self.adv.map()
        t = m.tile(self._selected(self.list_tiles)) if m else None
        if t:
            self.edit_tile(t)

    def _delete_selected_tile(self):
        m = self.adv.map()
        t = m.tile(self._selected(self.list_tiles)) if m else None
        if t:
            self.delete_from(m.tiles, t)

    def check_coverage(self):
        m = self.adv.map()
        if not m:
            return
        w = coverage_warnings(m)
        QMessageBox.information(self, "Tile check", "\n".join(w) if w else "No gaps. Every map square is on a tile.")

    def follow_link_menu(self):
        m = self.adv.map()
        links = [r for r in (m.remarks if m else []) if r.link]
        if not links:
            self.statusBar().showMessage("This map has no special links. Add one with a DM note.", 4000)
            return
        names = [r.text for r in links]
        name, ok = QInputDialog.getItem(self, "Follow special link", "Link", names, 0, False)
        if ok:
            self.adv.follow_link(links[names.index(name)].link)
            self.center_on_table_tile()

    # ================================================================ markers
    def add_marker(self):
        m = self.adv.map()
        if not m:
            return
        name, ok = QInputDialog.getText(self, "Party marker", "Name", text=f"Party {len(self.adv.markers) + 1}")
        if not ok:
            return
        t = self.adv.table_tile()
        x, y = (t.x + t.w // 2 + 0.5, t.y + t.h // 2 + 0.5) if t else (0.5, 0.5)
        self.adv.push_undo()
        k = Marker(new_id(), name.strip() or "Party", m.id, x, y)
        self.adv.markers.append(k)
        self.adv.active_marker = k.id
        self.adv.touch(structure=True)
        self.set_tool("marker")

    def rename_marker(self, k=None):
        k = k if isinstance(k, Marker) else self.adv.marker(self._selected(self.list_markers))
        if not k:
            return
        name, ok = QInputDialog.getText(self, "Rename marker", "Name", text=k.name)
        if ok and name.strip():
            self.adv.push_undo()
            k.name = name.strip()
            self.adv.touch(structure=True)

    def set_active_marker(self, marker_id):
        self.adv.active_marker = marker_id
        self.adv.touch(structure=True)

    def _delete_selected_marker(self):
        k = self.adv.marker(self._selected(self.list_markers))
        if k:
            self.delete_from(self.adv.markers, k)

    # ================================================================ remarks and table marks
    def add_remark_at(self, mp: QPointF):
        dlg = RemarkDialog(self, self.adv)
        if not dlg.exec():
            return
        text, popup, link = dlg.values()
        if not text:
            return
        self.adv.push_undo()
        fog = self.adv.map_fog()
        revealed = fog is not None and not fog.is_fogged(mp.x(), mp.y())
        self.adv.map().remarks.append(Remark(new_id(), mp.x(), mp.y(), text, popup, revealed, link))
        self.adv.touch(structure=True)

    def edit_remark(self, r: Remark):
        dlg = RemarkDialog(self, self.adv, r)
        if dlg.exec():
            text, popup, link = dlg.values()
            self.adv.push_undo()
            r.text, r.popup, r.link = text or r.text, popup, link
            self.adv.touch(structure=True)

    def add_table_text_at(self, mp: QPointF):
        dlg = TableTextDialog(self, "", 0)
        if dlg.exec():
            text, facing = dlg.values()
            if text:
                self.adv.push_undo()
                k = TableMark(new_id(), "text", mp.x(), mp.y(), text=text,
                              rotation={0: 0.0, 90: 90.0, 180: 180.0, 270: -90.0}[facing],
                              fill="#F4EBD6", stroke=self.pal_stroke or "#2C2C2A", opacity=1.0,
                              text_size=self.pal_tsize.value(), dm_only=self.pal_dm.isChecked())
                self.adv.map().marks.append(k)
                self.map_view.set_selection([("mark", k)])
                self.adv.touch(structure=True)

    def edit_table_text(self, k: TableMark):
        facing = ROTATION_TO_FACING.get(round(k.rotation), 0)
        dlg = TableTextDialog(self, k.text, facing)
        if dlg.exec():
            text, new_facing = dlg.values()
            self.adv.push_undo()
            k.text = text or k.text
            if new_facing != facing:
                k.rotation = {0: 0.0, 90: 90.0, 180: 180.0, 270: -90.0}[new_facing]
            self.adv.touch(structure=True)

    def _remark_obj(self, item):
        sel, m = item.data(Qt.UserRole) if item else None, self.adv.map()
        if not sel or not m:
            return None, None
        kind, oid = sel
        lst = m.remarks if kind == "remark" else m.marks
        return kind, next((o for o in lst if o.id == oid), None)

    def _remark_clicked(self, item):
        kind, obj = self._remark_obj(item)
        if obj:
            self.map_view.set_selection([(kind, obj)])

    def _remark_double_clicked(self, item):
        kind, obj = self._remark_obj(item)
        if obj:
            self.map_view.center_on_point(obj.x, obj.y)

    def delete_from(self, lst: list, obj):
        self.adv.push_undo()
        lst.remove(obj)
        if isinstance(obj, Marker) and self.adv.active_marker == obj.id:
            self.adv.active_marker = self.adv.markers[0].id if self.adv.markers else None
        self.adv.touch(structure=True)

    # ================================================================ maps and parts
    def _map_chosen(self, index):
        self.adv.current_map = self.map_combo.itemData(index)
        self.map_view.set_selection([])
        self.adv.touch(structure=True)
        self.center_on_table_tile()

    def new_map(self, name=None):
        name = name or f"Map {len(self.adv.maps) + 1}"
        self.adv.push_undo()
        m = GameMap(new_id(), name)
        self.adv.maps.append(m)
        self.adv.current_map = m.id
        self.adv.touch(structure=True)
        return m

    def rename_map(self):
        m = self.adv.map()
        if not m:
            return
        name, ok = QInputDialog.getText(self, "Rename map", "Name", text=m.name)
        if ok and name.strip():
            self.adv.push_undo()
            m.name = name.strip()
            self.adv.touch(structure=True)

    def delete_map(self):
        m = self.adv.map()
        if not m:
            return
        if QMessageBox.question(self, "Delete map", f"Delete the map “{m.name}” with its tiles, "
                                                    f"fog and remarks? You can undo this.") != QMessageBox.Yes:
            return
        self.adv.push_undo()
        self.adv.maps.remove(m)
        self.adv.current_map = self.adv.maps[0].id if self.adv.maps else None
        self.adv.touch(structure=True)

    def import_maps(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import map images or PDFs", "", importer.IMAGE_TYPES)
        if not paths:
            return
        dlg = ImportDialog(self, self.adv, any(p.lower().endswith(".pdf") for p in paths))
        if not dlg.exec():
            return
        target = self.adv.map(dlg.target.currentData()) if dlg.target.currentData() else None
        if target is None:
            target = self.new_map(dlg.name.text().strip() or None)
        else:
            self.adv.push_undo()
            self.adv.current_map = target.id
        try:
            importer.import_files(self.adv, paths, target, dlg.dpi.value(), float(dlg.cell.value()))
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Import", str(e))
        self.adv.touch(structure=True)
        self.set_prep(True)
        self.fit_map()

    def _part_clicked(self, item):
        m = self.adv.map()
        part = next((p for p in m.parts if p.id == item.data(Qt.UserRole)), None) if m else None
        if part:
            self.set_tool("select")
            self.map_view.set_selection([("part", part)])

    def _selected_part(self):
        return self.map_view.selected_part()

    def align_grid(self, part, a: QPointF, b: QPointF):
        r = QRectF(a, b).normalized()
        if r.width() < 0.5 or r.height() < 0.5:
            self.map_view.show_toast("Drag over a larger block of squares.", 3000)
            return
        inv, ok = part.image_to_squares().inverted()
        img = inv.mapRect(r)
        dlg = GridDialog(self, round(r.width()), round(r.height()))
        if not dlg.exec():
            return
        self.adv.push_undo()
        part.cell_px = (img.width() / dlg.cols.value() + img.height() / dlg.rows.value()) / 2
        part.ox, part.oy = img.left(), img.top()
        part.gx, part.gy = round(r.left()), round(r.top())
        part.aligned = True
        self.adv.touch(structure=True)

    def _reset_crop(self):
        part = self._selected_part()
        if part and not part.locked:
            self.adv.push_undo()
            part.crop = None
            self.adv.touch(structure=True)

    def _mark_squares(self, on=True):
        part = self._selected_part()
        self.map_view.grid_mark = bool(on and part)
        if self.map_view.grid_mark:
            self.map_view.show_toast("Drag over a block of whole squares on this part.", 5000)
        self.refresh_selection_panel()

    def _set_part_grid(self, attr, value):
        part = self._selected_part()
        if self._updating_panel or part is None:
            return
        if part.locked:
            self.map_view.show_toast("This part is locked.", 2500)
            self.refresh_selection_panel()
            return
        self.adv.push_undo("grid_" + attr)
        setattr(part, attr, value)
        part.aligned = True
        self.adv.touch()
        self.refresh_selection_panel()

    def rotate_part(self, part):
        if part.locked:
            self.map_view.show_toast("This part is locked.", 2500)
            return
        self.adv.push_undo()
        try:
            importer.rotate_part(self.adv, part)
        except ValueError as e:
            QMessageBox.warning(self, "Rotate", str(e))
        self.adv.touch(structure=True)

    def tile_from_part(self, part):
        m = self.adv.map()
        b = part.bounds()
        tw, th = self.setup.tile_size()
        if abs(b.width() - tw) > 1 or abs(b.height() - th) > 1:
            self.warn(f"This part is {b.width():.0f} × {b.height():.0f} squares; the table shows {tw} × {th}.")
        self.adv.push_undo()
        t = Tile(new_id(), self.next_tile_name(m), math.floor(b.left() + 0.01), math.floor(b.top() + 0.01), tw, th)
        m.tiles.append(t)
        if not m.tile(self.adv.current_tile.get(m.id)):
            self.adv.current_tile[m.id] = t.id
        self.adv.touch(structure=True)

    def _rotate_selected_part(self):
        p = self._selected_part()
        if p:
            self.rotate_part(p)

    def _tile_from_selected_part(self):
        p = self._selected_part()
        if p:
            self.tile_from_part(p)

    # ================================================================ undo
    def undo(self):
        self.adv.undo()

    def redo(self):
        self.adv.redo()
