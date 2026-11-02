# D&D Table Map

Projector map tool for in-person D&D. The DM controls everything on their own
screen; a projector shows the current part of the map on the table at true
mini scale (1 square = 1 inch).

## Start

1. Once: install Python 3.10+, then run
   `python -m pip install --user -r requirements.txt`
2. Double-click **`Start Table Map.bat`** (or run `python -m dndmap` to see
   error messages).

With the projector connected as a second monitor, the table window opens full
screen on it. **F11** switches it between full screen and a normal window.

## Prepare a map (Prep mode)

1. **Table › Table setup**: pick the projector, enter the projected width and
   height on the table in mm and the square size (25.4 mm = 1 inch).
2. **Import** a map image or PDF (Ctrl+I).
3. **Select** tool (Q), click the map. In the side panel under **Grid**:
   **Mark squares on the map**, drag over e.g. 4 × 4 squares, enter the count.
   Fine-tune **Square** and **Offset** until the gold lines match the map.
   Drag the gold borders to crop.
4. **Tile** tool: click to place table-sized tiles; let neighbours overlap a little.

## Run a session (Live mode)

| Do | How |
| --- | --- |
| Show a tile / next tile | Click it in the side panel / arrow keys |
| Reveal fog | Reveal brush **V**, rectangle **E**, polygon **O**; hide **H** |
| Prepare without players seeing | Freeze **F**, then publish **Enter** |
| Black out the table | Panic **B** (press again to restore) |
| Measure | Ruler **R**, range **C**, template **T**; show on table **S**, pin **P** |
| Party position | Party marker **M**; after a tile change, put minis on the ghosts, then **G** |
| Notes | DM-only note **N**; marks for players **K** (shapes, text, PNG objects) |

## Edit things

**Q** selects. Drag to move, handles to resize or rotate, Shift-click or drag a
box for several. **Del** deletes, **Ctrl+C / Ctrl+V** copy and paste,
**Ctrl+] / Ctrl+[** front and back, hold **Alt** to place without snapping.
Colours, size, **DM only** and **Locked** are in the side panel.
**Esc** clears, **Ctrl+Z / Ctrl+Y** undo and redo, **Help › Hotkeys** lists all keys.

## Files

Each adventure is a folder (map images, fog, `adventure.json`) and saves
itself automatically. **File** › New adventure, Open adventure, Save adventure
as, Show adventure folder. PNG objects live in a shared library folder
(Documents/DndMaps/Objects by default).

Requirements: [v1-requirements.md](v1-requirements.md). Code: Python + PySide6 in `dndmap/`.
