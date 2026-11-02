"""Importing images and PDFs into map parts, and rotating parts."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageReader, QTransform

from dndmap.model import Adventure, GameMap, MapPart, new_id

IMAGE_TYPES = "Maps (*.png *.jpg *.jpeg *.webp *.pdf);;Images (*.png *.jpg *.jpeg *.webp);;PDF (*.pdf)"


def _pdf_pages(path: str, dpi: int) -> list[QImage]:
    from PySide6.QtPdf import QPdfDocument
    doc = QPdfDocument(None)
    err = doc.load(path)
    if err != QPdfDocument.Error.None_ or doc.pageCount() == 0:
        raise ValueError(f"Could not read the PDF ({err.name}).")
    pages = []
    for i in range(doc.pageCount()):
        pt = doc.pagePointSize(i)
        size = QSize(round(pt.width() * dpi / 72), round(pt.height() * dpi / 72))
        img = doc.render(i, size)
        if img.isNull():
            raise ValueError(f"Could not render page {i + 1}.")
        pages.append(img.convertToFormat(QImage.Format_RGB32))
    doc.close()
    return pages


def import_files(adv: Adventure, paths: list[str], game_map: GameMap, pdf_dpi=150, cell_px=70.0) -> int:
    """Add each image (and each PDF page) as a part, placed to the right of what is there."""
    added = 0
    for path in paths:
        if path.lower().endswith(".pdf"):
            images = [(adv.add_image(img), img.width(), img.height(), float(pdf_dpi))
                      for img in _pdf_pages(path, pdf_dpi)]
        else:
            reader = QImageReader(path)
            size = reader.size()
            if not size.isValid():
                raise ValueError(f"Could not read the image {os.path.basename(path)}.")
            images = [(adv.copy_image_file(path), size.width(), size.height(), cell_px)]
        for name, w, h, cell in images:
            b = game_map.bounds()
            gx = int(b.right()) + 1 if not b.isNull() else 0
            gy = int(b.top()) if not b.isNull() else 0
            game_map.parts.append(MapPart(new_id(), name, w, h, cell, 0.0, 0.0, gx, gy))
            added += 1
    return added


def rotate_part(adv: Adventure, part: MapPart):
    """Rotate a part's image 90 degrees clockwise. Grid alignment and crop are reset."""
    img = QImage(adv.image_path(part.image))
    if img.isNull():
        raise ValueError("The part's image file is missing.")
    rotated = img.transformed(QTransform().rotate(90))
    part.image = adv.add_image(rotated)
    part.w, part.h = rotated.width(), rotated.height()
    part.crop = None
    part.ox = part.oy = 0.0
