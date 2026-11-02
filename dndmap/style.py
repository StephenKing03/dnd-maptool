"""Colours, fonts and the Qt style sheet (UI-1, UI-1a)."""
from __future__ import annotations

import glob
import os

from PySide6.QtGui import QColor, QFont, QFontDatabase

BROWN = QColor("#854F0B")
GOLD = QColor("#BA7517")
GOLD_LIGHT = QColor("#EF9F27")
PARCHMENT = QColor("#F4EBD6")
PARCHMENT_HL = QColor("#FAEEDA")
INK = QColor("#2C2C2A")
INK_TEXT = QColor("#633806")
RULER = QColor("#A32D2D")
RULER_TEXT = QColor("#791F1F")
FOG_DM = QColor("#5F5E5A")
MARKER = QColor("#0F6E56")
MARKER_FILL = QColor("#E1F5EE")
GHOST = QColor("#EF9F27")

_serif = "Georgia"
_display = "Georgia"


def load_fonts():
    """Use Cinzel for headings if its .ttf files are in assets/fonts, else a plain serif."""
    global _serif, _display
    here = os.path.dirname(os.path.abspath(__file__))
    for path in glob.glob(os.path.join(here, "..", "assets", "fonts", "*.ttf")):
        fid = QFontDatabase.addApplicationFont(path)
        for fam in QFontDatabase.applicationFontFamilies(fid):
            if fam.lower().startswith("cinzel"):
                _display = fam
    families = set(QFontDatabase.families())
    if "Georgia" not in families:
        _serif = next((f for f in ("DejaVu Serif", "Liberation Serif", "Noto Serif") if f in families), "serif")
        if _display == "Georgia":
            _display = _serif


def display_font(px: float) -> QFont:
    f = QFont(_display)
    f.setPixelSize(max(1, int(round(px))))
    f.setLetterSpacing(QFont.PercentageSpacing, 106)
    return f


def note_font(px: float) -> QFont:
    f = QFont(_serif)
    f.setPixelSize(max(1, int(round(px))))
    f.setItalic(True)
    return f


def display_family() -> str:
    return _display


def stylesheet() -> str:
    d = _display
    return f"""
QMainWindow, QWidget#central {{ background: #FBF8F1; }}
QWidget {{ font-size: 12px; color: #2C2C2A; }}
QMenuBar {{ background: #F1EDE3; border-bottom: 1px solid rgba(133,79,11,90); }}
QMenuBar::item:selected, QMenu::item:selected {{ background: #FAEEDA; color: #633806; }}
QMenu {{ background: #FFFFFF; border: 1px solid #854F0B; }}
QFrame#header {{ background: #F1EDE3; border-bottom: 1px solid #854F0B; }}
QLabel#title {{ font-family: "{d}"; font-size: 16px; }}
QLabel#cap {{ font-family: "{d}"; font-size: 11px; color: #BA7517; }}
QFrame#toolbar {{ background: #F1EDE3; border-bottom: 1px solid rgba(133,79,11,90); }}
QFrame#group {{ border: none; border-right: 1px solid rgba(133,79,11,77); }}
QToolButton, QPushButton {{
    border: 1px solid rgba(133,79,11,115); border-radius: 2px; background: #FFFFFF;
    padding: 2px 7px; min-height: 18px;
}}
QToolButton:hover, QPushButton:hover {{ background: #FBF4E6; }}
QToolButton:checked, QPushButton:checked {{ background: #FAEEDA; color: #633806; border-color: #BA7517; }}
QToolButton#swatch {{ padding: 0; min-height: 0; border: 1px solid transparent; background: transparent; }}
QToolButton#swatch:checked {{ border: 2px solid #BA7517; background: #FAEEDA; }}
QToolButton#panic {{ color: #A32D2D; border-color: #E24B4A; }}
QToolButton#panic:checked {{ background: #A32D2D; color: #FFFFFF; }}
QFrame#side {{ background: #FFFFFF; border-left: 1px solid rgba(133,79,11,90); }}
QLabel#sideHead {{
    font-family: "{d}"; font-size: 11px; color: #BA7517;
    border-bottom: 3px double rgba(133,79,11,115); padding: 6px 2px 1px 2px;
}}
QListWidget {{ border: 1px solid rgba(133,79,11,60); background: #FFFFFF; }}
QListWidget::item:selected {{ background: #FAEEDA; color: #633806; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {{
    border: 1px solid rgba(133,79,11,115); border-radius: 2px; background: #FFFFFF; padding: 1px 4px;
}}
QStatusBar {{ background: #F1EDE3; border-top: 1px solid #854F0B; }}
QStatusBar QLabel {{ padding: 0 8px; color: #5F5E5A; }}
QLabel#modeLive {{ color: #3B6D11; }}
QLabel#modeFrozen {{ color: #FFFFFF; background: #185FA5; }}
QLabel#modePanic {{ color: #FFFFFF; background: #A32D2D; }}
QLabel#warn {{ color: #A32D2D; }}
QDialog {{ background: #FBF8F1; }}
"""
