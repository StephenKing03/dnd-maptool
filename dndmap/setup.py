"""Table hardware settings, stored per computer (not per adventure)."""
from __future__ import annotations

import math
import os

from PySide6.QtCore import QSettings, QStandardPaths


class TableSetup:
    def __init__(self):
        # DNDMAP_SETTINGS lets test runs use their own settings instead of the real ones
        self._s = QSettings("dndmap", os.environ.get("DNDMAP_SETTINGS", "dndmap"))
        self.screen = str(self._s.value("screen", ""))
        self.width_mm = float(self._s.value("width_mm", 1016.0))
        self.height_mm = float(self._s.value("height_mm", 610.0))
        self.square_mm = float(self._s.value("square_mm", 25.4))
        self.rule = str(self._s.value("rule", "5e"))
        self.last_folder = str(self._s.value("last_folder", ""))
        self.library_folder = str(self._s.value("library_folder", "")) or os.path.join(
            os.path.dirname(self.default_folder()), "Objects")
        self.show_grid = str(self._s.value("show_grid", "false")).lower() == "true"

    def save(self):
        for key in ("screen", "width_mm", "height_mm", "square_mm", "rule", "last_folder", "library_folder",
                    "show_grid"):
            self._s.setValue(key, getattr(self, key))
        self._s.sync()

    def tile_size(self) -> tuple[int, int]:
        """Number of whole squares the table shows (SET-4)."""
        return (max(1, math.floor(self.width_mm / self.square_mm + 1e-6)),
                max(1, math.floor(self.height_mm / self.square_mm + 1e-6)))

    def pixels_per_square(self, screen) -> float:
        """Logical pixels per square on the projector screen, independent of OS scaling (NFR-1)."""
        return screen.geometry().width() / self.width_mm * self.square_mm

    @staticmethod
    def default_folder() -> str:
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
        return os.path.join(docs, "DndMaps", "My adventure")
