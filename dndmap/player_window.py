"""The table (projector) window and the small table preview on the DM screen."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from dndmap import render, style


class PlayerWindow(QWidget):
    """Shows the current tile at true scale when full screen on the projector."""

    def __init__(self, win):
        super().__init__(None)
        self.win = win
        self.setWindowTitle("Table view")
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.resize(960, 600)

    def paintEvent(self, _):
        adv, setup = self.win.adv, self.win.setup
        p = QPainter(self)
        pps = setup.pixels_per_square(self.screen()) if self.isFullScreen() else None
        render.render_player(p, QRectF(self.rect()), adv.player_state(), adv.image_path,
                             adv.live_overlay, setup.rule, pps, adv.panic)

    def projector_screen(self):
        screens = QGuiApplication.screens()
        named = next((s for s in screens if s.name() == self.win.setup.screen), None)
        if named and named != self.win.screen():
            return named
        others = [s for s in screens if s != self.win.screen()]
        return others[0] if others else None

    def show_on_projector(self, fullscreen: bool):
        screen = self.projector_screen() if fullscreen else None
        if screen is None:
            self.setCursor(Qt.ArrowCursor)
            self.showNormal()
            return False
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.BlankCursor)
        self.showFullScreen()
        return True

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F11:
            self.show_on_projector(not self.isFullScreen())
        else:
            self.win.handle_table_key(e)


class TablePreview(QWidget):
    """Small picture of what the table shows (or will show after publishing, while frozen)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(130)

    def sizeHint(self):
        return QSize(200, 130)

    def paintEvent(self, _):
        adv = self.win.adv
        p = QPainter(self)
        state = adv.live_state()
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if state.tile is None:
            p.fillRect(area, QColor("black"))
            p.setPen(QColor("#B4B2A9"))
            p.setFont(style.note_font(12))
            p.drawText(area, Qt.AlignCenter, "No tile on the table")
        else:
            render.render_player(p, area, state, adv.image_path, adv.live_overlay, self.win.setup.rule,
                                 None, adv.panic)
        p.setPen(style.BROWN)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
