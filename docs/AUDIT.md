# Audit (in progress, 2026-11-11)

First pass of the Fable sprint audit. These findings come from reading the code only. **None has
been tested in Blender yet**, and nothing is fixed. The sprint stopped at a usage limit; the next
session picks up from "Next steps".

## Findings, ranked by likely impact

1. **Subdivision Surface distortion also gets printed.** blender-3mf-io applies modifiers on
   export (`use_mesh_modifiers=True`), so the printed UVs are the subdivided ones. Decal UVs are a
   flat projection written on the base mesh. Subsurf then smooths the UVs (UV Smooth "Keep
   Boundaries") separately from the geometry. In layer mode, faces outside the decal have (0,0) in
   the decal's UV map, so the island boundary is a seam. Candidate fixes, best first:
   (a) a Geometry Nodes step at the end of the modifier stack that writes the decal UV from final
   positions (exact, and placement follows edits; needs a check that the exporter reads it);
   (b) fit on the evaluated mesh;
   (c) document it as a limitation.
   Measure before choosing.
2. **Undo probably desyncs the pixels.** Image pixel buffers aren't part of memfile undo, so
   Ctrl+Z restores the text setting but likely leaves the new pixels in place. Fix: an `undo_post`
   / `redo_post` handler that redraws decals whose settings no longer match what was drawn
   (a Python-side cache keyed by `session_uid`). Needs testing in a real window.
3. **Every slider move packs the image** (`img.pack()` in `update_decal`): a PNG encode of up to
   8192 px for each tick of a drag. Pack in a `save_pre` handler instead.
4. **Each redraw renders the text up to three times through a temporary PNG**: two `_ink_box`
   renders ("Hg" every time) plus the final render. Cache ink boxes per (font id, text), and skip
   re-rendering the coverage for colour-only changes.
5. **Resolution (owner's feedback #2).** At 20 px/mm a 2 mm decal is about 32 px (blurry) and a
   160 mm one is 3200 px. Proposal: pixels = max(print resolution × size, a minimum of about
   256 px for the text height), capped by a pixel budget. Remove the setting from the panel (at
   most an Advanced override), and add a legibility warning when the text is below an assumed
   minimum height (about 1.5 mm, to confirm on a printed part).
6. **Invisible in Solid shading (owner's feedback #3).** Proposal, beyond an outline or a badge:
   a GPU draw handler that draws the real decal texture over its faces in Solid mode (evaluated
   mesh, alpha blend, slight depth bias in a custom shader), toggled in the Overlays popover, plus
   a list of an object's decals in Object Mode. Show screenshots of 2 or 3 styles first.
7. **Remove leaves clutter.** The decal's `UVMap Layer k` stays on the mesh, and only the active
   object's slots are restored when the decal is on several objects.
8. **Panel location (owner's feedback #4).** Bucket Builder #38 has no implementation yet. Design
   a shared preference (Material tab / sidebar tab / Scene tab), re-registering the panel class
   with new `bl_space_type`/`bl_context`/`bl_category`, and coordinate the pattern with the
   Bucket Builder and Crosscut sessions.

## Next steps

Verify 1 and 2 in Blender, fix 2 to 4 and 7, then build 5 and 6 (screenshots of the 6 directions
first), then 8. Then the 0.5.0 build, tag, pre-release and Workbench row, as usual.
