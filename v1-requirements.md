# Table Projector Map - v1 Requirements

As of: 2026-10-31


## 1. Overview

Version 1 is a map tool for in-person D&D: the DM prepares and controls a map
on their private screen, and the players see a projected version of it on the
table at true mini scale. The goal is convenience and mechanically sound play,
not visual spectacle.

The core idea is ONE SCENE, TWO VIEWS: the DM view shows everything (fog as a
grey overlay, remarks, hidden areas), the player view shows only what has been
revealed. Every v1 feature is a property of that scene.

- DM: prepares maps, controls what the table shows, measures ranges and areas
  during play.
- Players: see the projected map, move their physical minis on it, follow
  ghost outlines on transitions.

Requirement IDs (for example MAP-1) are used so individual items can be
discussed, ticked off or changed.


## 2. Setup and platform

The software runs on one PC with two displays: the DM's monitor and the
projector as a second monitor.

- SET-1  One application drives both displays: the DM window on the main
         monitor, the player window full screen on the projector.
- SET-2  The projector is angled, not mounted straight down. Its keystone and
         geometry calibration is already done and is outside the software's
         scope.
- SET-3  One grid square is 5 ft in game and 1 inch (25 mm) on the table. The
         physical square size is a setting, entered once.
- SET-4  The number of squares visible on the table is calculated from the
         projector setup and the physical square size.
- SET-5  Target platform is Linux; development and testing happen on a Windows
         laptop. Both must behave the same.
- SET-6  Works fully offline during a session.
- SET-7  Interface language is English.
- SET-8  Players sit on all four sides of the table, so everything projected
         must be readable from every side.


## 3. Scope

Version 1 is developed and refined until the DM is happy with it; nothing from
later versions starts before that.

In v1:
- Map import with manual grid alignment
- Predefined tiles with arrow-key navigation
- Fog of war (eraser, polygon, re-hide)
- Freeze mode and panic button
- Measuring and AoE templates
- Party marker with ghost on transitions
- DM-only room remarks
- Player-visible remarks and pointers on the table
- Menu band, hotkeys, save and resume

Not in v1:
- Camera or webcam detection of any kind
- Movement range overlay
- Initiative tracker and condition durations
- Visual effects (fire, water, lighting)
- Dynamic line of sight
- Hex grids
- Handouts or images shown on the table
- Rotating the DM view to match the DM's seat
- Hiding secret details drawn into the map image


## 4. Map import

Import works the same for maps from any online map tool, so it relies on simple
DM input rather than tool-specific formats.

- MAP-1  Import PNG, JPG, WebP and PDF files. A PDF is converted to an image at
         a chosen resolution; each page of a multi-page PDF can become its own
         map part.
- MAP-2  Square grids only. The DM aligns the grid manually: mark two or three
         squares, or drag a grid overlay until it matches. Works for maps
         without a visible grid too.
- MAP-3  Each map stores its own grid alignment, since pixel size per square
         differs between maps.
- MAP-4  Crop borders, legends and margins on import.
- MAP-5  Rotate a map by 90 degree steps on import.
- MAP-6  Stitch pre-tiled exports: place the parts side by side and nudge them
         square by square until the grids line up. No automatic image
         matching.
- MAP-7  Organization: adventure -> maps -> tiles.
- MAP-8  Large images (many thousands of pixels per side) stay smooth to pan
         and zoom on the DM screen.
- MAP-9  A single map part or tile can be scaled on its own, for when it was
         exported at a different resolution than the rest. The DM aligns its
         grid separately, and the software scales it so its squares match the
         rest of the map and 1 inch on the table.
- MAP-10 Map parts are edited by selecting them (Prep mode, select tool). The
         selected part is isolated: everything else fades to semi-transparent.
- MAP-11 Crop: the selected part shows handles on its four borders and
         corners; the DM drags them to set the crop. Reset restores the full
         image. This replaces drawing a crop rectangle.
- MAP-12 Grid alignment (MAP-2), rotation (MAP-5) and moving (MAP-6) are done
         from the same part editing, not as separate tools.


## 5. Tiles and navigation

The table always shows exactly one predefined tile; the DM moves between tiles
in discrete jumps, never by free scrolling.

- TIL-1  The DM places tiles on a map as rectangles of exactly table size,
         snapped to the grid.
- TIL-2  Tiles may overlap so minis near an edge stay on the table after a
         transition.
- TIL-3  The software determines each tile's neighbour up, down, left and right
         from their positions. The DM can override a link where the layout is
         irregular.
- TIL-4  Arrow keys switch the table to the neighbouring tile in that
         direction.
- TIL-5  Special links connect tiles across maps or non-adjacent places
         (stairs, portals, trapdoors), each with an arrival point. They are
         triggered from the menu band or a remark pin.
- TIL-6  The DM can jump to any tile directly from a list.
- TIL-7  The software warns when neighbouring tiles leave a gap, or when part
         of a map is covered by no tile.
- TIL-8  A pre-tiled export whose parts match the table size can be imported
         directly as predefined tiles.


## 6. Fog of war

Fog is revealed manually by the DM; no wall geometry has to be defined.

- FOG-1  Every map starts fully fogged.
- FOG-2  Reveal with a freeform eraser brush; brush size adjustable in squares.
- FOG-3  Polygon reveal: click a room's corners to reveal it in one action,
         corners snapped to the grid.
- FOG-9  Rectangle reveal: drag a grid-snapped rectangle to reveal it; the
         same tool with Shift held hides it again.
- FOG-4  Re-hide brush to fog areas again.
- FOG-5  Players see fog as pure black, so minis in fogged areas are not lit.
- FOG-6  The DM sees fog as a grey, semi-transparent overlay, so the map
         underneath stays readable.
- FOG-7  Fog belongs to the map, not the tile: revealed areas stay revealed
         across tiles.
- FOG-8  Fog state is saved with the session and restored on resume.


## 7. Freeze mode and panic button

Freeze lets the DM prepare changes without the players seeing them; panic hides
the table instantly. They are separate controls.

- FRZ-1  Freeze keeps the table showing exactly what it showed when frozen.
- FRZ-2  While frozen, the DM can change anything: reveal fog, switch tiles,
         move the party marker, add remarks.
- FRZ-3  While frozen, the DM screen shows a preview of what the players will
         see after publishing.
- FRZ-4  Publish pushes all pending changes to the table at once and ends
         freeze.
- FRZ-5  Rulers and measurements still appear on the table live while frozen.
- FRZ-6  A clearly visible FROZEN indicator stays on the DM screen while
         frozen.
- PAN-1  One hotkey or button turns the whole table black immediately;
         pressing it again restores the previous view.


## 8. Measuring and templates

The DM controls all measurements with the mouse on the DM screen; results can
be shown on the table as overlays.

- MEA-1  Ruler from point to point, showing the distance in feet and squares
         ("25 ft · 5 sq"), with one dot per square along the line and a marker
         at each end.
- MEA-3  Range circle around a clicked square, for spell or weapon range.
- MEA-4  AoE templates: cone, sphere, line and cube, at correct size,
         highlighting the affected squares. The DM picks the shape and enters
         the size; the label shows only the size (for example "15 ft"), never
         a spell name.
- MEA-5  Diagonal rule: every diagonal counts 5 ft (5e default), switchable to
         5-10-5.
- MEA-6  A square counts as affected by an area when the area covers its
         center.
- MEA-7  Measurements are private on the DM screen by default; one key shows
         the current one on the table.
- MEA-8  Templates can be pinned so they stay on the table (Web, Spirit
         Guardians, Darkness) until removed. Unpinned ones clear with Esc.
- MEA-9  Labels on the table are short and readable from all sides (SET-8):
         a ruler label appears twice along the line, facing opposite sides,
         on small parchment plates. A template or range label appears four
         times around the shape, facing outward; on round shapes it is
         written along the curve of the ring.
- MEA-10 Rulers and templates have a light outline so they stay visible on
         any map colour under the projector.


## 9. Party marker and transitions

Without a camera, the software only knows where the party is from a marker the
DM places; a ghost on the table shows where that point moved after a tile
change.

- PRT-1  The DM places a party marker on a square on the DM screen.
- PRT-2  Up to a few markers for a split party, one of them active.
- PRT-3  On a tile change, the table shows a ghost outline at the marker's new
         position, calculated exactly from the tiles' map coordinates.
- PRT-4  If the marker would fall outside the new tile, the software warns the
         DM.
- PRT-5  On a special link (stairs, portal), the ghost appears at the link's
         arrival point instead.
- PRT-6  The ghost disappears when the DM confirms the minis are placed.
- PRT-7  Every marker keeps a "target position" separate from its actual
         position, so camera tracking or a robot can use the same concept
         later.


## 10. Remarks

There are two kinds of remarks: DM-only reminders (REM) and player-visible
remarks and pointers on the table (PRM). The software is not a full
note-taking tool.

- REM-1  The DM pins a short text remark to any point on a map.
- REM-2  Remarks are visible only on the DM screen, never on the table.
- REM-3  A remark can be linked to a fog area and pops up as a reminder when
         that area is revealed.
- REM-4  A remark can carry a special link (TIL-5), so stairs or portals can be
         triggered from it.
- PRM-1  The DM can place player-visible items on the map: a short text
         remark, an arrow pointing at something, or a circle highlighting an
         area.
- PRM-2  They stay until the DM removes them. They belong to a map position,
         so they show whenever that spot is on the table, and are saved with
         the session.
- PRM-3  The DM chooses which table side a text remark faces (90 degree
         steps), since players sit on all sides.
- PRM-4  Items placed in a fogged area stay hidden until that area is
         revealed.
- PRM-5  Adding, changing or removing them follows freeze and publish like
         other changes (unlike rulers, which show live).
- PRM-6  On the DM screen, player-visible items look clearly different from
         DM-only remarks.
- PRM-7  Each table text has its own size, set when placing it and changeable
         later (text height in squares).
- PRM-8  A mark palette offers basic shapes: rectangle, circle, triangle, line
         and arrow, plus text. Each has a size, rotation, fill colour, outline
         colour and opacity that can be changed after placing.
- PRM-9  A small set of colours chosen to read well under a projector, plus a
         custom colour picker.
- PRM-10 Image objects: the DM adds PNG files (with transparency) to an object
         library and places them on the map at any size and rotation.
- PRM-11 Shapes and image objects can be placed in Prep and Live mode, stay
         until removed, and follow PRM-2 to PRM-5 (saved, hidden under fog,
         freeze and publish).
- PRM-12 Any table text, shape or object can be marked "DM only": the DM sees
         it, the table does not, until the checkbox is cleared.
- PRM-13 The object library is shared by all adventures (one library folder);
         a placed object is copied into the adventure so it stays complete.


## 11. DM controls and sessions

The DM works from a menu band on the DM screen, with hotkeys for anything used
often during play.

- CTL-1  A menu band on the DM screen gives access to all tools and modes.
- CTL-2  Hotkeys for frequent actions at least: panic, freeze, publish, tile
         navigation (arrows), ruler, templates, show measurement on table,
         clear (Esc).
- CTL-3  Undo and redo for all DM actions (fog, tiles, markers, templates,
         remarks).
- CTL-4  The DM screen shows the map with fog overlay and remarks, the
         currently projected tile outlined, and the player preview while
         frozen.
- CTL-5  Prep mode for setting up maps, tiles and remarks; live mode for
         running the session.
- SEL-1  A select tool that only selects and moves: click an item to select
         it, drag to move it, drag its handles to resize or rotate it. It never
         paints fog, measures or places anything.
- SEL-2  Selectable: table texts, shapes, image objects, DM remarks, pinned
         templates and party markers; in Prep mode also tiles and map parts.
- SEL-3  The side panel shows the selected item's properties (text, size,
         colours, opacity, facing) for editing. Delete removes it, a
         double-click opens its full edit dialog.
- SEL-4  Multi-select with Shift-click or by dragging a box over empty map.
- SEL-5  Ctrl+C copies the selection, Ctrl+V pastes it at the mouse position.
- SEL-6  Items can be locked so they cannot be moved, resized or deleted by
         accident. Map parts are always locked in Live mode.
- SEL-7  Front/back order for overlapping items: bring to front, send to back.
- SEL-8  Moving and resizing snap to the grid (objects to square centres,
         shapes to grid lines); holding Alt places freely.
- SEL-9  With something selected, the arrow keys nudge it by one square;
         with nothing selected they switch tiles (TIL-4). Q picks the select
         tool, and Esc returns to it when there is nothing left to clear.
- SES-1  The session state (current tile, fog, markers, pinned templates) saves
         automatically.
- SES-2  A session can be resumed exactly where it stopped, including
         mid-dungeon.
- SES-3  The DM chooses where an adventure folder lives: New adventure asks
         for a name and a location, Save adventure as copies it to a new
         location, Open adventure opens any adventure folder.
- UI-1   Plain, functional look like a classic desktop tool: flat neutral
         greys, the standard system font, square controls with text labels.
         No gradients, glow, glass effects, large rounded cards, emoji icons or
         decorative animations.
- UI-1a  A light D&D touch on top of that, without overdoing it: a fantasy
         serif font for the title and panel headings only, warm brown and
         parchment tones for borders and the map, small line icons next to
         button labels, and classic dungeon-map styling (hatched rock, dark
         walls) for the map display.
- UI-2   Dense layout: the map takes most of the DM screen, with a tool bar on
         top, a narrow side panel and a status bar at the bottom.
- UI-3   Colour is used only where it carries meaning: fog, the projected
         tile, the frozen state and measurement overlays.


## 12. Non-functional requirements

Scale accuracy and cross-platform behaviour matter most, because the table only
works when one square is exactly one inch.

- NFR-1  Scale accuracy: one grid square on the table matches the physical
         square size within about 1 mm, regardless of operating system display
         scaling.
- NFR-2  The player window opens full screen on the projector monitor reliably
         on both Windows and Linux, including Linux desktops running Wayland.
- NFR-3  Tile switches, fog changes and publish appear on the table within a
         fraction of a second.
- NFR-4  Setting up a new map (import, grid, tiles, rooms) takes about 10
         minutes or less.
- NFR-5  No internet connection is needed during play.
- NFR-6  Test on the target Linux PC early in development, not only at the end.


## 13. Later versions

These are recorded so v1 does not block them; none is built before v1 is
finished.

- Hiding secret details in map images: to decide right after v1. DM/player
  image pairs and DM-painted cover patches that can be revealed later.
- Camera occupancy tracking (v2): detect occupied squares when the table is
  still; identity by object permanence. Infrared camera with reflective dots on
  mini bases is the preferred option, so decorative objects are ignored.
- Status rings and full ghost layout: conditions as rings around mini bases;
  ghosts for every mini on transitions; marching order.
- Auto-reveal radius: fog clears around tracked player minis, ignoring walls;
  switchable per room.
- Movement range overlay: reachable squares from a mini's speed, with a Dash
  band. Removed from v1 as too complicated for now.
- Initiative tracker: with condition and spell durations.
- Visual effects: built on pinned templates (MEA-8).
- Robot: under-table magnetic XY gantry moving monster minis. Add a steel
  washer or magnet to mini bases when printing.
