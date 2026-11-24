# Decisions and lessons

Why Decal Press is built the way it is, what didn't work, and what is still unconfirmed.
Newest first within each section.

## Requirements from the maintainer

| ID | Requirement (date) | Status |
| --- | --- | --- |
| R-010 | Answers on the vision (2026-11-23): the order of Flatten and Placement is ours to choose; sharp text always comes first; Dual Tone is a real target (5600 now, 1200 in about a year); the 580 and Dual Tone resolve the same, from a 600 dpi printhead with bleed to about the PA 12 grain; smallest text about 2 mm; build orientation doesn't change color | 0.5.0: D-009 |
| R-009 | "Not in a usable state": decals project through the part and show inverted on the back, mostly with text; test many parts at different scales, scale applied and not (2026-11-23) | 0.5.0: D-010, fixed |
| R-008 | A Flatten button that bakes the layers into one texture per part, also as a 3MF export option; both placement modes (on the surface, or exact faces) with a switch (2026-11-12) | Planned: VISION.md 0.6 and 0.7 |
| R-007 | Decals visible in Solid shading; no Resolution setting, the same look at any size; Subdivision distortion fixed or documented; a panel location preference shared with the other add-ons (2026-11-11) | 0.5.0: D-009, D-011, D-012, D-013 |
| R-006 | Weird results on real parts that aren't planar or rectangular; test on Suzanne and the like; rotate, translate and scale after placement (2026-11-10) | 0.4.0: D-007, D-008 |
| R-005 | Name with "decal" in it: Decal Press. Panel in the Material tab. ExtraBold weight (2026-11-10) | 0.4.0 |
| R-004 | Test on Blender 5.2 only; adjust compatibility claims or open issues rather than testing old versions (2026-11-09) | Manifest says 4.5+, untested; issue |
| R-003 | Replace Material's background defaults to the existing material's color; bundle the bolder of the free fonts; a failsafe when a font won't load (2026-11-09) | 0.3.0 |
| R-002 | Layer the decal over the existing material by default (black text, transparent background), Replace as an advanced option; image decals from a file or loaded images with a key color and fuzziness; default color pure black (2026-11-09) | 0.2.0 |
| R-001 | Select faces in Edit Mode, type text, get an image sized to the face height (width when too long) that redraws as the text changes and survives saves and 3MF export (2026-11-09) | 0.1.0 |

## Decisions

### D-013: Panel under the material slots, or in the sidebar (0.5.0)
0.4.0's panel sat below every built-in Material panel, off screen, and was easy to miss entirely.
It is now a sub-panel of the material slot list (one class for EEVEE/Workbench's slot panel, one
for Cycles'), so it comes right after the slots. The preference *Panel* (Material Properties or
Sidebar) and *Sidebar Tab* (default "Decal"; give several add-ons the same name to share a tab)
follow the portfolio review's D3. D3's advice stands: try both for a while, then keep one.

### D-012: Decals drawn in Solid shading (0.5.0)
A draw handler draws each decal's faces from the evaluated mesh with the decal image, clipped like
the print (CLIP), pulled slightly toward the viewer so it doesn't flicker against its face.
Batches are cached per object and rebuilt on depsgraph updates. Overlays > Objects > *Decals*
turns it off. An outline or a badge was the feedback's sketch; the real image shows what will
print and which way up, which is the point. The panel also lists every decal on the object (not
only the active face's), with a Select Faces button.

### D-011: Subdivision and other shape modifiers (0.5.0)
Most of the "odd distortion" was D-010 (Suzanne has no material). What is left is small: the
decal's UVs are subdivided by different rules from the surface, about 0.1 mm on average on a 20 mm
decal at level 2 (AUDIT.md). The panel says so when a shape-changing modifier is on, and suggests
applying it. An exact fix (a Geometry Nodes modifier writing the UVs from the final surface) isn't
worth its cost until a real part needs it.

### D-010: Every face gets a real material slot before a decal is added (0.5.0)
On an object with no material slot, every face has material index 0 and shows the last slot. The
decal's slot became that last slot, so the decal showed on every face, mirrored and upside down on
the back of the part. The same happened to faces whose index pointed past the last slot. Add now
creates an empty slot first and clamps indices, checks the selection before changing anything, and
gives each decal a UV map no other material on the object reads (an overlapping decal used to move
the first one). Remove works on every object, returns faces to their own slot and removes the
emptied slots, materials and UV map. `tests/blender/check_decals.py` covers all of it.

### D-009: Text resolution from the printer, not a setting (0.5.0)
The full-color 580 and Dual Tone print color from a 600 dpi printhead (0.042 mm dots), and ink bleed
blurs detail to about one powder grain: HP lists 60 um for PA 12 and 58 um for CB PA 12 (the 580's
powder). So no print shows detail finer than about 0.05 mm. Text images use two texels per printhead
dot, 48 px/mm (about 1200 dpi), the most a decal ever needs, favouring sharpness as asked. Small
decals get at least 256 px on their short side so they stay sharp on screen; large ones are capped
at 8192 px a side and 16 megapixels (above that, letters are tens of mm tall and still far finer
than the printer). The owner's smallest text is about 2 mm, so the panel warns below 2 mm.
The image's aspect ratio is kept exact, so text never stretches.

### D-008: Placement on top of the fit (0.4.0)
Offset (mm, along the decal's fitted axes), Rotation (any angle) and Scale (of the fitted size) only
rewrite UVs; Scale also redraws the image at the new size so the resolution holds. The fit rectangle
is stored on the image (`fit_rect`), so moving a slider doesn't search again. *Rotate 90°* stays:
it fits the decal along the other side of the faces, which re-sizes it, unlike Rotation. Layer
decals clip (CLIP) outside the image; Replace textures extend (EXTEND), so their edge pixels are
always the background color, or a moved decal would smear.

### D-007: Fit into the largest clear area, oriented by straight sides (0.4.0)
0.3.0 stretched the decal over the selection's bounding rectangle, aligned to its longest edge.
On real parts that put text off the face (L shapes, triangles, holes) and at random angles on round
or organic faces, where the longest edge is arbitrary. Now:
- Orientation: the smallest rectangle around the faces' convex hull, but only when hull edges
  along or across it make up 30% of the perimeter and it's at least 2% smaller than the
  world-aligned rectangle. Otherwise world-aligned (horizontal on walls, +X on flat faces). The
  long side carries the text unless it's nearly square (<1.25:1), then the more horizontal side.
- *Clear Area* (default) rasterizes the faces (about 96 cells on the long side, at most ~20k
  cells) and picks the covered rectangle where the content comes out biggest, then the biggest of
  those. Cell centres count, so the edges are shrunk half a cell; a fully covered grid uses the
  exact rectangle. Small triangles are rasterized in one numpy pass (6000 faces: about 0.8 s).
  *Whole Selection* keeps the old bounding rectangle.
- Still a flat projection: strongly curved selections stretch. Unwrapping (conformal) would follow
  the surface but loses the straight, measurable layout; left as an issue.

### D-006: Panel in the Material tab (0.4.0)
The 3D Viewport sidebar is crowded with the maintainer's other add-ons. The Material tab fits
because a decal is a material layer. Add-ons can't create new Properties tabs or slot a panel
between built-in ones, so it sits after the built-in panels (`bl_order` 1); users can drag it up.

### D-005: Bundled Nunito ExtraBold, with fallbacks (0.3.0, weight changed in 0.4.0)
Arial Rounded MT Bold (the maintainer's font) isn't redistributable. Nunito (OFL, no reserved font
names) is close in feel; the static ExtraBold (800) instance was made from the variable font with
fontTools, since none is published. A font that fails to load or draw falls back to the bundled one,
then bold system fonts, then Blender's UI font, with a warning on the decal.

### D-004: Layer over the material by default (0.2.0)
The decal is a texture layer in a copy of the face's material (Mix node, factor = alpha), the
pattern blender-3mf-io exports as `multiproperties`. Netfabb can't read layered textures, hence
*Replace Material*.

### D-003: Settings on the image (0.1.0)
Each decal is a packed Image with its settings in a PropertyGroup on it, so a .blend carries
everything and the decal can be found from any material that shows it.

### D-002: Text drawn with blf, not PIL (0.1.0)
`blf.bind_imbuf` draws text into an image buffer inside Blender (4.5+), so no third-party module is
needed. ImBuf has no Python pixel access, so pixels go through a temporary PNG.

### D-001: Name (0.4.0)
"Decal" was wanted in the name. Inkstamp was too close to Inkscape; Overprint was liked; Decal
Press chosen (2026-11-10).

## Open questions and assumptions

| ID | Assumption or question | Status |
| --- | --- | --- |
| Q-001 | Thresholds in D-007 (30% straight perimeter, 2%, 1.25:1) are guesses from synthetic shapes | Waiting on real parts |
| Q-002 | Offset is along the decal's own axes, not the turned decal's | Assumed |
| Q-003 | A decal used on two objects with different faces takes its size from the last one fitted | Known limitation |
| Q-004 | Layered decal 3MFs from blender-3mf-io open and print correctly in Magics/SmartStream on a 580 | Untested |
| Q-005 | 48 px/mm is enough for Dual Tone's halftoning as well as the 580's color | Assumed from the owner's "same resolution" |
| Q-006 | Replace Material decals write into the part's active UV map (the exporter reads plain textures from it), so Remove can't bring back those faces' original UVs | Known limitation; Flatten (VISION 0.6) replaces Replace |
| Q-007 | Linked duplicates share a mesh, so a decal shows on all of them | By design in Blender; the panel says so |
