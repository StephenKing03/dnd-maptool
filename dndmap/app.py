"""Application start: load the last adventure, open the DM window and the table window."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from dndmap import style
from dndmap.dm_window import MainWindow
from dndmap.model import Adventure
from dndmap.setup import TableSetup


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Table Map")
    style.load_fonts()
    app.setStyleSheet(style.stylesheet())
    setup = TableSetup()
    adv = Adventure.load(setup.last_folder or TableSetup.default_folder())
    win = MainWindow(adv, setup)
    win.show()
    win.show_player()
    win.activateWindow()
    sys.exit(app.exec())
