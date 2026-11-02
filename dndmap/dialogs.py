"""Small dialogs for remarks, table text, tiles, grid alignment, import and table setup."""
from __future__ import annotations

import os

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout)

from dndmap.geometry import DIRECTIONS

FACINGS = [("Bottom side", 0), ("Left side", 90), ("Top side", 180), ("Right side", 270)]


def _buttons(dlg: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


class RemarkDialog(QDialog):
    """DM-only remark with optional reveal reminder and special link."""

    def __init__(self, parent, adv, remark=None):
        super().__init__(parent)
        self.setWindowTitle("DM remark")
        self.adv = adv
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.text = QLineEdit(remark.text if remark else "")
        self.text.setPlaceholderText("Trap on chest, DC 14")
        self.popup = QCheckBox("Remind me when this spot is revealed")
        self.popup.setChecked(remark.popup if remark else True)
        form.addRow("Text", self.text)
        form.addRow("", self.popup)
        lay.addLayout(form)

        self.link_box = QGroupBox("Special link (stairs, portal, trapdoor)")
        self.link_box.setCheckable(True)
        link = remark.link if remark else None
        self.link_box.setChecked(bool(link))
        lf = QFormLayout(self.link_box)
        self.map_combo = QComboBox()
        for m in adv.maps:
            self.map_combo.addItem(m.name, m.id)
        self.tile_combo = QComboBox()
        self.ax, self.ay = QDoubleSpinBox(), QDoubleSpinBox()
        for s in (self.ax, self.ay):
            s.setRange(-10000, 10000)
            s.setDecimals(1)
            s.setSingleStep(1)
        lf.addRow("Map", self.map_combo)
        lf.addRow("Tile", self.tile_combo)
        lf.addRow("Arrival square x", self.ax)
        lf.addRow("Arrival square y", self.ay)
        lay.addWidget(self.link_box)
        lay.addWidget(_buttons(self))
        self.map_combo.currentIndexChanged.connect(self._fill_tiles)
        self.tile_combo.currentIndexChanged.connect(self._tile_center)
        if link:
            self.map_combo.setCurrentIndex(max(0, self.map_combo.findData(link.get("map"))))
        self._fill_tiles()
        if link:
            self.tile_combo.setCurrentIndex(max(0, self.tile_combo.findData(link.get("tile"))))
            self.ax.setValue(link.get("ax", 0))
            self.ay.setValue(link.get("ay", 0))

    def _fill_tiles(self):
        self.tile_combo.blockSignals(True)
        self.tile_combo.clear()
        m = self.adv.map(self.map_combo.currentData())
        for t in (m.tiles if m else []):
            self.tile_combo.addItem(t.name, t.id)
        self.tile_combo.blockSignals(False)
        self._tile_center()

    def _tile_center(self):
        m = self.adv.map(self.map_combo.currentData())
        t = m.tile(self.tile_combo.currentData()) if m else None
        if t:
            self.ax.setValue(t.x + t.w // 2 + 0.5)
            self.ay.setValue(t.y + t.h // 2 + 0.5)

    def values(self):
        link = None
        if self.link_box.isChecked() and self.tile_combo.currentData():
            link = {"map": self.map_combo.currentData(), "tile": self.tile_combo.currentData(),
                    "ax": self.ax.value(), "ay": self.ay.value()}
        return self.text.text().strip(), self.popup.isChecked(), link


class AdventureLocationDialog(QDialog):
    """Name and parent folder for a new adventure folder (SES-3)."""

    def __init__(self, parent, title: str, name: str, location: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        self.location = QLineEdit(location)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.location, 1)
        row.addWidget(browse)
        self.result_label = QLabel()
        self.result_label.setStyleSheet("color:#5F5E5A;")
        self.result_label.setWordWrap(True)
        form.addRow("Name", self.name)
        form.addRow("Location", row)
        form.addRow("", self.result_label)
        form.addRow(_buttons(self))
        self.name.textChanged.connect(self._update)
        self.location.textChanged.connect(self._update)
        self._update()

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose location", self.location.text())
        if folder:
            self.location.setText(folder)

    def _update(self):
        self.result_label.setText("Folder: " + self.path())

    def path(self) -> str:
        return os.path.join(self.location.text().strip(), self.name.text().strip())


class TableTextDialog(QDialog):
    def __init__(self, parent, text="", facing=0):
        super().__init__(parent)
        self.setWindowTitle("Text on the table")
        form = QFormLayout(self)
        self.text = QLineEdit(text)
        self.text.setPlaceholderText("A rusted lever")
        self.facing = QComboBox()
        for label, value in FACINGS:
            self.facing.addItem(label, value)
        self.facing.setCurrentIndex(max(0, self.facing.findData(facing)))
        form.addRow("Text", self.text)
        form.addRow("Readable from", self.facing)
        form.addRow(_buttons(self))

    def values(self):
        return self.text.text().strip(), self.facing.currentData()


class TileDialog(QDialog):
    def __init__(self, parent, game_map, tile):
        super().__init__(parent)
        self.setWindowTitle(f"Tile {tile.name}")
        form = QFormLayout(self)
        self.name = QLineEdit(tile.name)
        form.addRow("Name", self.name)
        self.combos = {}
        for d in DIRECTIONS:
            c = QComboBox()
            c.addItem("Automatic", "")
            for t in game_map.tiles:
                if t.id != tile.id:
                    c.addItem(t.name, t.id)
            c.setCurrentIndex(max(0, c.findData(tile.neighbours.get(d, ""))))
            self.combos[d] = c
            form.addRow(f"Neighbour {d}", c)
        form.addRow(_buttons(self))

    def values(self):
        return self.name.text().strip(), {d: c.currentData() for d, c in self.combos.items() if c.currentData()}


class GridDialog(QDialog):
    def __init__(self, parent, cols: int, rows: int):
        super().__init__(parent)
        self.setWindowTitle("Align grid")
        form = QFormLayout(self)
        form.addRow(QLabel("How many squares does the marked rectangle span?"))
        self.cols, self.rows = QSpinBox(), QSpinBox()
        for s, v in ((self.cols, cols), (self.rows, rows)):
            s.setRange(1, 500)
            s.setValue(max(1, v))
        form.addRow("Squares across", self.cols)
        form.addRow("Squares down", self.rows)
        form.addRow(_buttons(self))


class ImportDialog(QDialog):
    def __init__(self, parent, adv, has_pdf: bool):
        super().__init__(parent)
        self.setWindowTitle("Import map")
        form = QFormLayout(self)
        self.target = QComboBox()
        self.target.addItem("New map", "")
        for m in adv.maps:
            self.target.addItem(f"Add to “{m.name}”", m.id)
        if adv.current_map:
            self.target.setCurrentIndex(max(0, self.target.findData(adv.current_map)))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Level 1")
        self.cell = QSpinBox()
        self.cell.setRange(5, 1000)
        self.cell.setValue(70)
        self.cell.setSuffix(" px per square")
        self.dpi = QSpinBox()
        self.dpi.setRange(50, 600)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        form.addRow("Import into", self.target)
        form.addRow("New map name", self.name)
        form.addRow("Image grid (estimate)", self.cell)
        if has_pdf:
            form.addRow("PDF resolution", self.dpi)
        form.addRow(QLabel("Fine-tune the grid afterwards with the Grid tool in Prep mode."))
        form.addRow(_buttons(self))
        self.target.currentIndexChanged.connect(lambda: self.name.setEnabled(not self.target.currentData()))
        self.name.setEnabled(not self.target.currentData())


class TableSetupDialog(QDialog):
    def __init__(self, parent, setup):
        super().__init__(parent)
        self.setWindowTitle("Table setup")
        self.setup = setup
        form = QFormLayout(self)
        self.screen = QComboBox()
        for s in QGuiApplication.screens():
            g = s.geometry()
            self.screen.addItem(f"{s.name()} ({g.width()}×{g.height()})", s.name())
        self.screen.setCurrentIndex(max(0, self.screen.findData(setup.screen)))
        self.width, self.height, self.square = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for s, v in ((self.width, setup.width_mm), (self.height, setup.height_mm), (self.square, setup.square_mm)):
            s.setRange(1, 10000)
            s.setDecimals(1)
            s.setSuffix(" mm")
            s.setValue(v)
        self.rule = QComboBox()
        self.rule.addItem("Every diagonal 5 ft (5e)", "5e")
        self.rule.addItem("Alternating 5-10-5 ft", "5-10-5")
        self.rule.setCurrentIndex(max(0, self.rule.findData(setup.rule)))
        self.resize_tiles = QCheckBox("Resize existing tiles to the new table size")
        self.info = QLabel()
        form.addRow("Projector screen", self.screen)
        form.addRow("Projected width on table", self.width)
        form.addRow("Projected height on table", self.height)
        form.addRow("One square on table", self.square)
        form.addRow("Diagonals", self.rule)
        form.addRow("", self.info)
        form.addRow("", self.resize_tiles)
        form.addRow(_buttons(self))
        for s in (self.width, self.height, self.square):
            s.valueChanged.connect(self._update_info)
        self.screen.currentIndexChanged.connect(self._update_info)
        self._update_info()

    def _update_info(self):
        cols = int(self.width.value() // self.square.value())
        rows = int(self.height.value() // self.square.value())
        scr = next((s for s in QGuiApplication.screens() if s.name() == self.screen.currentData()), None)
        pps = scr.geometry().width() / self.width.value() * self.square.value() if scr else 0
        self.info.setText(f"Table shows {cols} × {rows} squares, {pps:.1f} px per square")

    def apply(self):
        s = self.setup
        s.screen = self.screen.currentData()
        s.width_mm, s.height_mm, s.square_mm = self.width.value(), self.height.value(), self.square.value()
        s.rule = self.rule.currentData()
        s.save()
