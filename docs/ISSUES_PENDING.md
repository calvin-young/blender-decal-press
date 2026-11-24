# Issues to file on GitHub

`gh` gets a 404 on this repo (its token doesn't include it yet), so the issues from the 0.5.0 bug
hunt wait here. File each as a GitHub issue with its label; close the fixed ones with "Fixed in
<commit>" and a link to that commit. Then delete this file.

## Fixed in 0.5.0

1. **[bug] Decal shows on every face of an object without a material, mirrored on the back.** On an
   object with no material slot every face has material index 0 and shows the last slot, which
   became the decal's slot. The decal showed on the whole part, mirrored and upside down on the
   back. Same for faces whose material index pointed past the last slot. On a closed cube the Add
   failed instead. Fixed in f76d249 (`_prepare_slots`).
2. **[bug] A decal over part of another moves the first one.** Both got the same UV map when the
   first selected face was a plain one. Fixed in f76d249 (UV map name unique per object).
3. **[bug] A failed Add leaves a half-made decal.** The image, material and slot were created
   before the selection was checked; the faces stayed reassigned. Fixed in f76d249.
4. **[bug] Remove leaves slots, materials and UV maps behind, and only works on the active object.**
   Fixed in f76d249.
5. **[bug] Undo restores a decal's text but not its image.** Fixed in 0.5.0 (`_on_undo`).
6. **[enhancement] Resolution setting: the same text should look the same at any size.** A 2 mm
   face got a 40 px image. Fixed in 0.5.0 (48 px/mm, at least 256 px; setting removed).
7. **[enhancement] Decals invisible in Solid shading.** Fixed in 0.5.0 (drawn in Solid; Overlays
   toggle; panel lists every decal).
8. **[enhancement] Panel location preference** (with calvin-young/blender-bucket-builder#38,
   calvin-young/blender-crosscut#18). Done in 0.5.0: Material Properties or Sidebar, and a Sidebar
   Tab name. The panel also moved up under the material slots: 0.4.0's was off screen.
9. **[enhancement] Subdivision Surface distortion.** Mostly issue 1 (Suzanne has no material). The
   remaining ~0.1 mm is documented, with a note in the panel. Closed as documented.

## Open

10. **[enhancement] Export test:** open a layered decal 3MF from blender-3mf-io in SmartStream and
    MiniMagics, then print it on a 580 (VISION 0.5, DECISIONS Q-004).
11. **[enhancement] Flatten:** bake a part's decal layers into one texture, also as a 3MF export
    option (owner's request, 2026-11-12; VISION 0.6).
12. **[enhancement] Two placement modes, on the surface or exact faces, with a switch** (owner's
    request, 2026-11-12; VISION 0.7).
13. **[enhancement] API for Bucket Builder's labeled copies:** `decals_on(obj)`, `add_text_decal`,
    `label_objects` with `{n}` / `{name}` tokens (VISION 0.8).
14. **[enhancement] Dual Tone:** grayscale mode and preview for the 5600 (and the 1200 later)
    (VISION 0.8).
15. **[bug] Replace Material overwrites the faces' UVs in the part's active map,** so Remove can't
    restore them. The exporter reads plain textures from the active map, so it can't simply use
    its own. Flatten will replace Replace Material (DECISIONS Q-006).
16. **[enhancement] Linked duplicates share their decals** (a shared mesh). The panel says so; a
    "make single user" button may help when labeling copies.
17. **[enhancement] Large decals redraw slowly:** an 80 mm label (4560 x 1776 px) takes about
    0.13 s per color change and 0.28 s per text change. Most of it is the image round trip through
    a file (imbuf has no pixel access from Python).
18. **[enhancement] Blender 4.5 untested** (manifest says 4.5+). **Curved selections** stretch
    (flat projection; AUDIT A1).
