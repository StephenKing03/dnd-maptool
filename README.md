# Table Map (v1 prototype)

Map software for in-person D&D with a projector on the table. The DM controls
everything on their own screen; the projector shows the current tile at true
mini scale. Requirements: [v1-requirements.md](v1-requirements.md).

## Install and run

Needs Python 3.10 or newer. Works on Windows and Linux.

```
python -m pip install --user -r requirements.txt
python -m dndmap
```

Run the second command from this folder, or double-click
`Start Table Map.bat` in this folder (Windows; right-click › Send to ›
Desktop for a shortcut). The terminal command shows error messages; the
double-click start does not. The DM window opens on your main
screen. With a projector connected as a second monitor, the table window goes
full screen on it; on a single screen it opens as a normal window for testing.
F11 switches the table window between full screen and windowed.

Optional: put the Cinzel font files (`Cinzel-*.ttf`, free from Google Fonts)
into `assets/fonts/` for the fantasy headings. Without them a plain serif font
is used.

## First session

1. **Table setup** (Table menu): pick the projector screen, enter the size of
   the projected picture on the table in mm and the size of one square
   (25.4 mm = 1 inch). The table then shows that many whole squares.
2. **Import** a map image or PDF (File › Import map, Ctrl+I). Prep mode turns on.
3. **Edit the map part**: with the Select tool, click the map. The part is
   isolated and the side panel shows its options. Under **Grid**, press
   **Mark squares on the map**, drag over a block of whole squares (e.g.
   4 × 4) and enter how many it covers. Fine-tune with **Square** (pixels per
   square) and **Offset** until the gold lines sit on the map's own lines.
   Drag the gold borders to crop, drag inside to line it up with other parts,
   rotate, lock it.
4. **Tile**: click to place table-sized tiles, drag to move them, let them
   overlap a little. Double-click a tile to rename it or override its
   neighbours.
5. Switch to **Live**. Click a tile in the side panel to put it on the table;
   the arrow keys then move between neighbouring tiles.

## Marks on the table

The **Table mark** tool opens the mark palette: rectangle, circle, triangle,
line, arrow and text, with fill and outline colours and opacity. Drag to draw,
click for one square. Below it, **Objects** lists PNG files from the shared
object library (Add PNG… copies files into it). Everything placed can be
selected, moved, resized, rotated, locked, set to "DM only", copied and
reordered with the **Select** tool; its options appear in the side panel.

## Hotkeys

| Key | Action |
| --- | --- |
| Arrow keys | Nudge the selection; with nothing selected, show the neighbouring tile |
| Q | Select tool (Esc also returns to it) |
| Delete | Delete the selection |
| Ctrl+C / Ctrl+V | Copy / paste at the mouse |
| Ctrl+] / Ctrl+[ | Bring to front / send to back |
| Alt (held) | Move, resize or place without snapping |
| F / Enter | Freeze / publish (publish ends freeze) |
| B | Panic: table black, press again to restore |
| G | Minis placed (hides ghost outlines) |
| V, E, O, H | Reveal brush, rectangle (Shift: hide), polygon reveal, hide brush |
| [ and ] | Smaller / larger brush |
| R, C, T | Ruler, range circle, template |
| S | Show the current measurement on the table |
| P | Pin the current template |
| Esc | Clear measurement or polygon |
| M, N, K | Party marker, DM note, table mark |
| L | Follow a special link (stairs, portal) |
| Home | Center on the table tile |
| Ctrl+Z / Ctrl+Y | Undo / redo |

Right-drag or middle-drag pans, the mouse wheel zooms, right-click on an item
opens its menu (edit, delete, follow link, unpin).

## Where things are saved

Each adventure is a folder with `adventure.json`, the imported images and
placed objects, and the fog of each map. File › New adventure and Save
adventure as… let you choose name and location; Open adventure opens any
adventure folder; Show adventure folder opens it in the file browser. It saves
automatically every few seconds and when you close the program, and opens the
last adventure on start. The object library is a separate folder shared by
all adventures (default `Documents/DndMaps/Objects`).

## Code layout

| File | What it does |
| --- | --- |
| `dndmap/model.py` | Adventure, maps, parts, tiles, fog, marks, freeze state, undo, saving |
| `dndmap/geometry.py` | Distances, template squares, tile neighbours, gap check |
| `dndmap/render.py` | All drawing, shared by DM view, table and preview |
| `dndmap/map_view.py` | The DM's interactive map: select tool and all other tools |
| `dndmap/marks.py` | Shapes, texts and objects: hit tests, handles, snapping |
| `dndmap/dm_window.py` | DM window: toolbar, side panel, menus, hotkeys |
| `dndmap/player_window.py` | Table window and the small preview |
| `dndmap/dialogs.py`, `importer.py`, `setup.py` | Dialogs, image/PDF import, table settings |
