# Vision

Where Decal Press is going, in what order, and what is still missing. Written 2026-11-12, at
0.4.0. The reasoning is in [AUDIT.md](AUDIT.md) ("Direction"); this file is the plan. Everything
here is planned, not built. Milestones are proposals until the owner confirms them.

## What it is for

Someone who runs a full-color printer puts a label, logo or code on a part in under a minute, sees
exactly what will print, and gets a file that every program between Blender and the printer reads
correctly. With Bucket Builder, the same person labels forty numbered copies in one step.

It is not a texture painter, not a game-art decal tool, and not for engraved or embossed labels
(those are Bucket Builder's, see [AUDIT.md](AUDIT.md), "Overlap").

## Principles

- **What you see is what prints.** A decal is visible in every viewport mode and listed on its
  object; nothing prints that the user wasn't shown.
- **The part's mesh is never changed.** A decal is color on the surface.
- **The user doesn't need to know the file format.** Decals are always authored as layers. Making
  them readable elsewhere is a button, not a choice made before adding.
- **Sizes are in mm and checked against the printer.** No pixel settings.
- **Proven on prints.** Thresholds (smallest letter, smallest code module, contrast) come from
  printed test parts, not guesses.

## Milestones

Each is one or a few builds. The order follows value and risk; the one thing that can reorder it
is the export test in 0.5.

### 0.5 Trustworthy
The four feedback items of 2026-11-11 and the audit's bugs. No change to how decals are stored.
0.5.0 and 0.5.1 (2026-11-24/26) deliver all of it except the printer-software test:
- **Export test:** the XML is checked (tests/blender/check_export.py). Still open: the file
  opened in SmartStream and MiniMagics (Windows VM), then printed on the 580 (#10). If layers
  aren't read, 0.6 becomes urgent.
- Done: bugs B1 to B6 (objects without materials, overlap, remove, failed adds), tests that assert,
  undo.
- Done: decals drawn in Solid shading, a list of every decal on the object, `decals_on(obj)` for
  Bucket Builder's export check.
- Done: no Resolution setting; resolution from the printer (DECISIONS D-009); Letter Height.
- Done: panel location preference (Material Properties or Sidebar).
- Done: a note when a modifier changes the shape under a decal.

### 0.6 Flatten (owner's request 5)
One button turns a part's layers into one ordinary texture, and the 3MF exporter can do the same
on export.
- **Flatten Decals** on an object: one image, one UV map, one material per part. Undo restores
  the layers.
- For a part with a plain color (most parts): a small atlas where each decal's faces get an
  island at full print resolution and all other faces share a swatch of the base color. One image,
  and the text stays sharp.
- For a part that already has a texture: the decals are baked into a copy of it, enlarged where
  needed so the decal reaches print resolution, with a warning when it can't.
- **Export option in blender-3mf-io:** "Layered textures: Keep or Flatten", working on a copy so
  the scene keeps its editable layers. The flatten code is one file with no Decal Press imports,
  written here and kept identical in the fork (the portfolio review rules out a shared library).
  To agree with the 3MF session.
- "Replace Material" is removed: Flatten does its job, for any base and any number of decals,
  without overwriting the part's UVs (B3).
- This also ends the hard dependency on the fork's unreleased layered-textures branch: a flattened
  part exports with any exporter, to 3MF, OBJ or GLB.

This revises the audit's "Change 3", which proposed one opaque image per decal. One atlas per part
is what the owner asked for and is better, as long as decal islands keep their own resolution.

### 0.7 Placement (owner's request 6)
A decal becomes a placement on the part; where it is stored moves from the image to the mesh
(audit, changes 1 and 2). This changes saved data, so it comes before the features that build on it.
- **On Surface** (the default): click on the part to place, drag to move, a handle to turn and
  size. No Edit Mode. The faces under the decal are worked out and follow it.
- **Exact Faces:** the decal belongs to faces chosen by hand and is cut off at their edge, as
  today, with today's fit into the clear area.
- **A switch on each decal.** Both modes are the same record with one flag: whether the faces are
  worked out or pinned. Switching to Exact Faces pins the current faces; switching back releases
  them. Nothing moves when switching.
- **Pick Flat Area** for Exact Faces: grow the selection from one face across a flat region.
- Speed on large parts (audit P1, P2), since dragging has to feel live.
- Decals made in 0.4 to 0.6 are converted on load, as Exact Faces.

### 0.8 Labels
Variable content, and the meeting point with Bucket Builder's labeled copies (#39).
- Text tokens: `{name}`, `{n}`, kept up to date per object.
- A Python API: `add_text_decal`, `label_objects`, `remove_decal`.
- The shared "label spot" record that Bucket Builder also reads, for printed or engraved labels.
- One decal applied to many selected objects.
- Several lines and alignment.
- Legibility checks (letter height, stroke width, contrast), a backing box, automatic black or
  white text.
- Dual Tone (5600, later the 1200): a grayscale mode and a preview of how the decal prints.

### 0.9 Reach
Each is independent; order by demand.
- Text that follows cylinders.
- QR and Data Matrix codes.
- Saved styles (a company label layout, a logo).
- Adopting decals from an imported layered 3MF.

### 1.0 Proven
- A printed test sheet on the 580 sets the thresholds used by the checks.
- Tested on the current Blender LTS releases the manifest claims.
- Listed on the Blender extensions platform, with a demo video and a user guide.

## What's missing today

- **Evidence.** Nothing made by this add-on has been printed, or opened in the printer's software.
- **Real parts.** All testing is on synthetic shapes; the owner's test on real parts is still open.
- **A pushed repository and filed issues.** The roadmap lives in these documents until the token
  works.
- **Numbers from the printer:** the smallest code module (QR, Data Matrix), from a test print. The
  resolution, smallest letter and orientation answers are in.
- **Scripts other than Latin.** The bundled font covers Latin, Cyrillic and Vietnamese, but not Greek,
  Arabic, Hebrew, Chinese, Japanese or Korean. What a decal shows for those is untested.
- **The preview chain.** Crosscut's 580 color preview and Bucket Builder's export check don't know
  about decals yet.

## Answers from the owner (2026-11-23)

1. **Order of Flatten and Placement:** ours to choose; a larger overhaul is coming anyway. Kept as
   written: Flatten (0.6) is smaller and makes every file usable.
2. **Texture size when flattening:** sharp text always comes first; image size won't be a problem
   short of paragraphs of text. So Flatten enlarges a textured part's image where a decal needs it.
3. **Dual Tone** is commercially available on the 5600 and about a year out on the 1200: a real
   target alongside the 580, not a someday item. The grayscale mode and preview move from 0.9 to
   0.8.
4. **The printer's numbers:** the 580 and Dual Tone resolve the same, from a 600 dpi printhead with
   ink bleeding to about the PA 12 grain (HP lists 55-60 um). Smallest text about 2 mm. Build
   orientation doesn't change color. 0.5.0 uses this for its resolution (DECISIONS D-009).
