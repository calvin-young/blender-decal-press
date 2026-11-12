# Audit, 2026-11-12

A review of Decal Press 0.4.0 (`decal_press/__init__.py`, 1000 lines; `tests/blender/shapes.py`).
Review only: nothing here is fixed yet. Line numbers are for commit `8565313`.

What was run: the shape test (passes, 7 s), and one experiment script on Suzanne with a
Subdivision Surface modifier that measured UV error and timings (Blender 5.2.3, background).
Everything else comes from reading the code and is marked **(read)**; the builder should
reproduce each before fixing it.

## The short version

1. The add-on breaks on an object that has no material, which is what an imported part or a
   fresh Suzanne is. This is probably most of the "odd distortion" in the owner's feedback.
2. The approach (one packed image per decal, a Mix layer per decal, its own UV map) is right for
   layered 3MF and should stay. The flat projection is right for labels on flat faces.
3. The workflow's weak point is face selection. Real print parts are dense triangle meshes, and
   selecting a flat region by hand in Edit Mode is the hard part of adding a label. A "pick the
   flat area under this face" step would help more than any of the four feedback items.
4. Remove and Replace Material both damage things they shouldn't (slots, UV maps, the part's own
   UVs).
5. Nothing is asserted by a test. The no-material bug survived because the test always adds a
   material first.

## Bugs, ranked

### B1. Object with no material: the decal takes over every face (measured)
`_slot_index` (496-501) appends the decal material as slot 0, which every face already uses.
`fit_decal` (675-677) then treats all faces as the decal's. On Suzanne the fit covered 500 faces
instead of the 260 selected, and the decal came out 35.9 mm wide instead of 20.8 mm. In Replace
mode the whole part turns the background color.
**Fix:** in `DECALPRESS_OT_add.execute` (797), when the object has no slots, append an empty slot
first so the decal lands in slot 1. Handle `material_index >= len(slots)` the same way. Add a test.

### B2. A decal over part of another decal overwrites it (read)
`_free_layer_uv(first)` (397-404, called at 814) only looks at the first face's material. Select
faces that span decal A (uses `UVMap Layer 1`) and plain faces, with a plain face first: the new
decal also gets `UVMap Layer 1` and rewrites A's UVs on the shared faces.
**Fix:** take the UV names in use from every base material in the selection, not the first.

### B3. Replace Material overwrites the part's own UVs (read)
In Replace mode `s.uv_map` is empty, so `fit_decal` (714-716) writes into the active UV map. On a
textured part that destroys the texture mapping of those faces, and Remove doesn't bring it back.
**Fix:** give Replace decals their own UV map and a UV Map node, like layers. First check that
blender-3mf-io's plain-texture export path reads the UV Map node (its layered path does:
`export_3mf/layers.py` 77-85, 344).

### B4. Remove leaves things behind (read)
`DECALPRESS_OT_remove` (879-895):
- restores slots only on the active object; a decal used on other objects stays half removed, and
  the image stays listed as a decal because it still has users;
- puts the base material back into the decal's slot, so the object ends with two slots holding the
  same material, one more for each add and remove;
- never deletes the decal's UV map (a mesh holds at most 8).
**Fix:** loop over `decal_objects(img)`; move the faces back to the base material's original slot
and delete the emptied slot; delete the UV map when no other decal on the mesh uses it.

### B5. A failed Add leaves a half-made decal (read)
`execute` creates the image, materials and slots, assigns faces, and only then finds out the fit
failed (831-833). It returns CANCELLED with all of that in place.
**Fix:** test the selection (area, normal) before creating anything, or undo the changes on failure.
The message "faces have no area" is also wrong for the common cause, a selection that wraps all the
way round a part (the averaged normal is zero, 685). Say "Select faces on one side of the part".

### B6. Font warnings can show on the wrong decal (read)
`font_warnings` (50, 149, 920) is keyed by `as_pointer()`, which changes on undo and file load.
**Fix:** key by `session_uid`, and clear on `load_post`.

### B7. Editing the base material later doesn't reach the decal's faces (read, by design)
`layered_copy` (407-438) copies the base material. Change the part's color afterwards and the decal
faces keep the old one. A material can't vary per face, so the copy is needed.
**Fix:** on Refit (and at export through the API, see A3) rebuild the copy from the base, or show
"base material changed: Refresh" in the panel. Low priority; document it now.

### Not confirmed: undo
Images are packed on every change (231), so undo most likely restores the right pixels. It wasn't
tested, because it needs a real window. One check: type text, change it, Ctrl+Z, compare the image.

## Performance

Measured on Suzanne's cheek (260 faces):

| Step | 718 x 205 px | 2871 x 820 px |
| --- | --- | --- |
| Draw the text (`decal_pixels`) | 68 ms | 228 ms |
| Pack (`img.pack`) | 5 ms | 95 ms |
| Whole redraw (`update_decal`) | 72 ms | 325 ms |
| Refit with search | 169 ms | 421 ms |

So a slider drag runs at 3 to 14 updates a second, on a small mesh.

- **P1. Text is rendered three times per redraw, each through a temporary PNG** (`_ink_box` twice
  at 150-154, then 163; the round trip is 116-129). **Fix:** cache ink boxes per (font, text), and
  cache the coverage per (font, text, size, margin) so a color change only recolors. Try an
  uncompressed format for the round trip (untested).
- **P2. Object Mode edits convert the whole mesh to BMesh and back on every tick** (`refit`
  741-746), and `fit_decal` walks every face in Python (677, 689-695). On a real part of a few
  hundred thousand triangles each tick will take seconds (not measured). **Fix:** cache the decal's
  loop indices and projected coordinates per (object, decal); for placement-only changes write UVs
  with `foreach_set`. Keep BMesh for Edit Mode only.
- **P3. Pack on save, not on every change,** once P1 is done and undo is confirmed to survive it
  (a `save_pre` handler). 95 ms of the 325 ms at the larger size.
- **P4.** `decal_materials` (393) scans every material's nodes on each update. Fine today; cache
  if scenes get large.

## Architecture

- **A1. Split flatten, fit, place and draw.** `fit_decal` (667-722) projects, fits, places and
  writes UVs in one function. Make the first step "flatten these faces to 2D mm coordinates". Today
  that is the planar projection. A second flattener (Blender's unwrap, for selections whose normals
  spread more than about 10°) would then give true-length text on cylinders, the most common curved
  face on real parts, with the same fit and placement code. This is the existing curved-selection
  issue, and it's the right-sized re-architecture.
- **A2. Make the image the content, not the face.** Both `_text_pixels` (144-168) and
  `_image_pixels` (186-200) pad the image to the fit rectangle's shape. Layer decals clip outside
  the image, so the image only needs the text or picture plus its margin. That removes the padding
  code and makes resolution depend only on the content (see feedback item 2).
- **A3. A Python API with no scene state.** Add works only as an operator, in Edit Mode, reading
  `scene.decal_press_new`. The portfolio review (D6, item 4) proposes that Decal Press owns printed
  labels and Bucket Builder's numbered copies call it. That needs `add_text_decal(obj, faces, text,
  ...)`, `decals_on(obj)` (also for the export gate's "decals you may not know about"), and
  `remove_decal`. The operators become thin wrappers.
- **A4. One decal per object.** A duplicated part shares its decal image, so editing one label
  edits both, and the size comes from whichever was fitted last (Q-003). Numbered copies need
  "make this decal single-user" (copy the image and material), done automatically by the API.
- **A5. Split the file** into `draw.py`, `fit.py`, `materials.py`, `ui.py`, `api.py` when A1 and
  A3 are done. Not before: the single file isn't the problem.

## Tests

`shapes.py` renders pictures and asserts nothing. Add a background test file with asserts:
- object with no material (B1), overlapping decals (B2), Replace on a textured part (B3), add then
  remove leaves slots, materials, UV maps and UVs as they were (B4);
- the fitted rectangle's corners lie inside the selected faces, for every shape in `shapes.py`;
- the same text on a cube of radius 1 and radius 100 gives the same image size (feedback item 2);
- export through `io_mesh_3mf.api.export_3mf` when installed: `multiproperties` and
  `tilestyleu="none"` present.
Keep `shapes.py` for pictures.

## UX

- **U1. Face selection is the real cost.** Add **Pick Flat Area**: from the active face, grow
  across edges below a small angle (Blender's `mesh.faces_select_linked_flat` does this). Later, a
  click-on-the-part tool that does it from Object Mode. With A3, Bucket Builder can use the same
  code to choose a label face by itself.
- **U2. The panel shows only the decals of the material under the active face** (963, 768). Show
  every decal on the object, in both modes, with a Select Faces button on each. See feedback item 1.
- **U3. "Rotate 90°" and "Rotation" sit together and do different things** (938, 942). Rename the
  button "Turn to Other Side", or fold it into Fit.
- **U4. The info line** "20.8 x 10.1 mm, 417 x 203 px, layer" (944-946) is for developers. Show the
  letter height in mm, and warn when it's below what prints legibly (threshold to be set from a
  print; 1.5 mm is a guess).
- **U5. Layer or Replace can only be chosen before adding** (978-981). Let a decal switch.
- **U6.** `bl_order = 1` (954) doesn't put the panel under the slots; the README already says so.

## The four feedback items

### 1. Decals are invisible in Solid shading
**Recommend:** draw the real decals in Solid mode. A viewport draw handler draws each decal's faces
(from the evaluated mesh) with its image, alpha-blended, pulled slightly toward the camera in a
small custom shader so it doesn't flicker against the surface. Rebuild a decal's batch only when
its object or image changes. A "Decals" checkbox in the viewport's Overlays popover turns it off.
It belongs to the scene layer in the portfolio review's draw-order decision (D4).
Add two things with it: the object-wide list (U2) with a count in the panel header, and
`decals_on(obj)` for Bucket Builder's export gate.
**Not recommended:** an outline or a badge alone. They say a decal exists but not what it says or
whether it's upside down.
The builder should send screenshots of the textured overlay, and of the overlay plus a thin outline
around the decal's faces, before finishing one.

### 2. The Resolution setting
The cause: a fixed 20 px/mm (146, 310-312) gives 40 px on a 2 mm face and 4000 px on a 200 mm one.
**Recommend:** remove the setting. Pick the image size from the content: 24 px/mm (about 600 dpi),
but never fewer than 512 px or more than 4096 px on the long side. Both numbers are proposals; the
first should be checked against the 580's effective color resolution. With A2 this is one line.
One number in the add-on preferences ("Print resolution, dpi") is enough for anyone who needs it.

### 3. Distortion under a Subdivision Surface modifier
Two causes:
- **B1.** A fresh Suzanne has no material, so the decal was fitted across the whole head. Fix B1
  and test again before anything else.
- **A real, smaller effect (measured).** The decal's UVs are subdivided by different rules from the
  surface. On the 20.8 mm cheek decal at level 2, UVs were off by 0.08 mm on average and 1.4 mm at
  worst; with UV Smooth set to None, 0.18 mm on average. The exporter applies modifiers, so the
  print would show it too. Writing matching UVs on the ring of faces around the decal was tried
  and didn't help enough (average 0.05 mm, worst unchanged).
**Recommend:** don't build machinery for it. Print parts are imported meshes with no modifiers;
Suzanne with Subdivision is a demo case. Show a line in the panel when the object has a modifier
that changes its shape ("Subdivision moves the surface under this decal. Apply it for exact
placement.") with an Apply button, and document it.
The exact fix, if real parts turn out to need it: a Geometry Nodes modifier at the end of the stack
that writes the decal's UVs from the final positions. About a day, plus a check that the exporter
reads it.

### 4. Panel location
**Recommend:** follow the portfolio review, D3. Two preferences with the same names and wording as
Crosscut #18: `panel_location` ("Material Properties", the default here, or "Sidebar") and
`sidebar_tab` (default "Decal"). The update callback unregisters the panel class, changes
`bl_space_type`, `bl_region_type`, `bl_context` and `bl_category`, and registers it again. I agree
with D3's pushback: use it for two weeks, then keep one location and drop the setting.

## Order for the builder

1. B1 with a test, then re-test the Subdivision case.
2. B2 to B5, with tests.
3. A2 and feedback item 2 (resolution), P1.
4. Feedback item 1 (overlay, list, `decals_on`), with screenshots first.
5. U1 Pick Flat Area, U3, U4.
6. Feedback item 4 (panel location), feedback item 3 (warning line).
7. A3 API and A4, when Bucket Builder's labeled copies (#39) start. A1 with the curved-selection
   issue. P2 when a real part proves slow.
