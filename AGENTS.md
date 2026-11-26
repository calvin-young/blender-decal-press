# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
The human-facing overview is in [README.md](README.md).

## Project at a glance

- **What it is:** a Blender add-on that puts text or image decals on selected faces as textures,
  layered over the faces' material (layered 3MF) or replacing it, for full-color printing.
- **Status:** in development (0.5.2, 2026-11-26). Tested on Blender 5.2.3 only.
- **Runs in:** Blender 4.5+ as an extension (`decal_press/blender_manifest.toml`).

## Setup, test, package

- **Install for development:** `ln -s "$PWD/decal_press" ~/.config/blender/<version>/extensions/user_default/decal_press`,
  then enable "Decal Press" in Preferences > Add-ons.
- **Checks (run before every build):** `blender -b --factory-startup --python tests/blender/check_decals.py`
  adds text decals on 8 shapes x 4 sizes x 6 transforms, with and without materials, and checks
  that only the selected faces show them, not mirrored or upside down, not stretched, with enough
  pixels; then sequences (overlap, remove, undo-free leftovers, letter height, save and reopen,
  panel location). About 75 s. Exit status 1 on any failure.
- **Window checks:** `tests/blender/window.sh check_undo.py` (undo restores pixels; needs a real
  window) and `tests/blender/window.sh screenshots.py --out DIR` (front, back, Solid, the panel).
  `window.sh` uses a throwaway user config so no splash covers the view.
- **Shape renders:** `blender -b --factory-startup --python tests/blender/shapes.py` renders decals on
  awkward synthetic shapes to `~/decal_press_tests/`. Look at the images; nothing judges them.
- **3MF export check:** `MF=<folder with io_mesh_3mf> blender -b --factory-startup --python
  tests/blender/check_export.py`, with the fork's layered-texture export (e.g. `git -C
  ~/dev/blender-3mf-io archive test-all-prs io_mesh_3mf | tar -x -C /tmp/mf`). Checks the XML.
- **Build a zip:** `cd decal_press && zip -r ../decal_press-<version>.zip . -x "__pycache__/*"`.
  Bump `version` in the manifest first.

## Layout

```
decal_press/__init__.py   everything: drawing (blf), settings on the Image, materials, UV fit, operators, panel
decal_press/fonts/        Nunito ExtraBold (static instance of the variable font, OFL)
tests/blender/            check_decals.py (asserts), check_export.py (3MF XML, needs the 3MF fork),
                          check_undo.py and screenshots.py (real window, run through window.sh),
                          shapes.py (renders)
docs/                     DECISIONS.md, PROMPT_STATS.md, images for the README
```

## Conventions

- 1 Blender unit = 1 mm.
- A decal's settings live on its Image (`Image.decal_press`), so they travel with the packed image.
- The layered node pattern (Mix RGBA factor = texture alpha, A = below, B = decal, UV Map node,
  extension CLIP) is what blender-3mf-io's `layers.py` recognizes. Change both together.
- Property updates: content changes find the fit again (`_on_content`), placement only rewrites
  UVs (`_on_place`), size changes rewrite UVs and redraw (`_on_scale`), looks only redraw
  (`_on_change`).
- Every face has a real material slot before a decal slot is added (`_prepare_slots`); each decal
  has its own UV map; Remove leaves no slots, materials or UV maps behind. Tests check this.
- Images are packed on save (`save_pre`), not on every change. Undo restores settings but not
  pixels, so `undo_post` redraws decals whose settings no longer match what was drawn (`_drawn`).
- Fitting reads the mesh with numpy (`_mesh_array`): through the attribute API in Object Mode
  (10-80x faster than the legacy collections), through the legacy ones in Edit Mode, where
  `mesh.attributes` shows the edit mesh's layers instead of the synced mesh.
- Every decal UV lies inside its image: the image covers the faces' extent (`canvas`) and the
  decal is pasted into it (`_compose`). Readers repeat textures outside the image. Tests check it.
- Text resolution: 48 px/mm (two texels per 600 dpi printhead dot), at least 256 px short side,
  at most 8192 px a side and 16 MP (DECISIONS D-009).
- SPDX `GPL-3.0-or-later` header on every source file.
- UI/UX matters more to the maintainer than code style.

## Where knowledge lives

Work moves between sessions and assistants, so anything a future session needs is written into this
repo and pushed. Current state and next steps go here, the reasons behind decisions go in
`docs/DECISIONS.md`, bugs and planned features go in GitHub Issues.

## State and next steps

Updated 2026-11-26 at the end of the sprint session (hand-over to a fresh thread).

- **Version:** 0.5.2, pre-release on GitHub, Workbench row up to date. History in
  [CHANGELOG.md](CHANGELOG.md). Unreleased on main: nothing.
- **Builds:** every build gets a version bump, an annotated tag, a GitHub pre-release with the zip,
  a new download link on the Workbench row (ai-context, topics/workstation.md) and the zip sent to
  the owner first. Before a build, run `check_decals.py`, `window.sh check_undo.py`,
  `window.sh screenshots.py` (look at them) and `check_export.py`, then install the zip in a fresh
  config (`BLENDER_USER_CONFIG`/`BLENDER_USER_EXTENSIONS` in a temp folder, `blender --command
  extension install-file`, `addon_utils.enable(..., default_set=True)`) and add a decal.
- **Repo:** `calvin-young/blender-decal-press` (renamed from `decal-press`; git follows the
  redirect, `gh` needs the new name).
- **Milestone 0.5 "Trustworthy" (VISION.md):** done except a real print. 0.5.0 fixed the owner's
  "projected through, inverted on the back" (objects with no material slot) and five more bugs,
  and delivered the 2026-11-11 feedback; 0.5.1 tight fit, font fix after opening a file,
  multi-object Add, numpy fitting; 0.5.2 images cover all their faces (D-014), `decals_on(obj)`.
- **Readers (#10, tested 2026-11-26 in the Windows VM):** MiniMagics 23.5 shows layered, Replace,
  overlapping and no-material decals correctly. SmartStream 2.0 shows Replace decals; layered
  decal faces show gray (it shows one layer; the owner says layered files print on the 580 through
  the printer's API). Both repeat textures outside the image whatever `tilestyle` says, hence
  D-014. **Still open on #10: print a decal on the 580** (needs the owner). Test files come from
  `OUT=~/decal_press_tests/export check_export.py`; the VM helpers are in
  ai-context `tools/windows-vm/reader-benchmark/` (copy to a scratchpad, fix the paths).
- **Owner's answers (2026-11-23, DECISIONS R-010, D-009):** Flatten/Placement order is ours;
  sharp text first, image size won't matter; Dual Tone is a real target (5600 now, 1200 in about
  a year); the 580 and Dual Tone resolve the same (600 dpi head, bleed to about the PA 12 grain,
  55-60 um per HP); smallest text about 2 mm; build orientation doesn't change color.
- **Open issues:** #10 (580 print), #11 Flatten (0.6, next big item), #12 two placement modes
  (0.7), #13 API for Bucket Builder's labeled copies (0.8; Bucket Builder may get in touch about
  2D labels; `decals_on` exists), #14 Dual Tone (0.8), #15 Replace overwrites the active UV map
  (goes away with Flatten), #16 linked duplicates share decals, #17 speed (Edit Mode on dense
  meshes is the slow case: 1.4 s per step at 1.3M faces; a cache of the decal's corners would
  fix it), #18 Blender 4.5 untested.
- **Suggested next steps:** the owner's test of 0.5.2 on real parts (none yet); #17 Edit Mode
  cache; then 0.6 Flatten (#11), shared by copy with the 3MF fork's export option (agree with the
  3MF session; see the fork's AUDIT item 7 in ai-context).
- **Owner decisions pending:** keep the panel in Material Properties or the Sidebar after trying
  both (portfolio D3); the 580 print.
- **For other add-ons:** `decals_on(obj)` (in `__init__.py`) lists an object's decals with their
  text, size and problems, for Bucket Builder's export check (portfolio D6).
- [docs/AUDIT.md](docs/AUDIT.md) (2026-11-12) and [docs/VISION.md](docs/VISION.md) hold the review
  and the plan; AUDIT's bugs, P1, P3 and the four feedback items are done.
- Known limits: curved selections stretch (flat projection, AUDIT A1); Subdivision moves the
  surface under a decal by about 0.1 mm (D-011).

## Before you change things

- Read [docs/DECISIONS.md](docs/DECISIONS.md). The roadmap is in
  [GitHub Issues](https://github.com/calvin-young/blender-decal-press/issues).
- Update [docs/PROMPT_STATS.md](docs/PROMPT_STATS.md) at the end of each working session.

## Data

Tests and examples use synthetic geometry and generic names. Never commit real production or
customer data, real file paths, or fonts that can't be redistributed.

## Pull requests

Finish and test first, submit once, one logical change per PR, fill in the template including
**Requested vs. assumed**. AI-made commits end with `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
