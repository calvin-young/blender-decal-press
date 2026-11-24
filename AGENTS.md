# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
The human-facing overview is in [README.md](README.md).

## Project at a glance

- **What it is:** a Blender add-on that puts text or image decals on selected faces as textures,
  layered over the faces' material (layered 3MF) or replacing it, for full-color printing.
- **Status:** in development (0.5.0, 2026-11-24). Tested on Blender 5.2.3 only.
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
- **3MF export check (needs blender-3mf-io on the layered-textures branch):** not in the repo yet;
  export a layered decal with `io_mesh_3mf.api.export_3mf` and look for `<m:multiproperties` and
  `tilestyleu="none"` in `3D/3dmodel.model`.
- **Build a zip:** `cd decal_press && zip -r ../decal_press-<version>.zip . -x "__pycache__/*"`.
  Bump `version` in the manifest first.

## Layout

```
decal_press/__init__.py   everything: drawing (blf), settings on the Image, materials, UV fit, operators, panel
decal_press/fonts/        Nunito ExtraBold (static instance of the variable font, OFL)
tests/blender/            check_decals.py (asserts), check_undo.py and screenshots.py (real window,
                          run through window.sh), shapes.py (renders)
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
- Text resolution: 48 px/mm (two texels per 600 dpi printhead dot), at least 256 px short side,
  at most 8192 px a side and 16 MP (DECISIONS D-009).
- SPDX `GPL-3.0-or-later` header on every source file.
- UI/UX matters more to the maintainer than code style.

## Where knowledge lives

Work moves between sessions and assistants, so anything a future session needs is written into this
repo and pushed. Current state and next steps go here, the reasons behind decisions go in
`docs/DECISIONS.md`, bugs and planned features go in GitHub Issues.

## State and next steps

- History is in [CHANGELOG.md](CHANGELOG.md).
- **Builds:** every build gets a tag, a GitHub pre-release with the zip, and a new download link on
  the Workbench row (see ai-context, topics/workstation.md). Attach the zip at the top of the reply.
- **0.5.0 (2026-11-24)** fixed the owner's "projected through, inverted on the back" (objects
  without a material slot) and the other bugs from a bug hunt, and delivered the 2026-11-11 feedback
  (Solid shading, no Resolution setting, panel location, modifier note). See CHANGELOG.
- **Issues:** `gh` can't see this repo yet (404, although git pushes). The bugs found and fixed,
  and the open items, are in [docs/ISSUES_PENDING.md](docs/ISSUES_PENDING.md): file them as GitHub
  issues once `gh` has access (close the fixed ones with a link to the commit), then delete the file.
- **Next (VISION.md):** the export test (a layered decal 3MF in SmartStream and MiniMagics in the
  Windows VM, then a print); `decals_on(obj)` and the API for Bucket Builder's labeled copies
  (Bucket Builder may contact this project about 2D labels); 0.6 Flatten; 0.7 Placement.
- [docs/AUDIT.md](docs/AUDIT.md) (2026-11-12) and [docs/VISION.md](docs/VISION.md) hold the review
  and the plan. AUDIT's B1 to B6, P1, P3 and the four feedback items are done in 0.5.0.
- Open: the maintainer's test on real parts; Blender 4.5 untested; curved selections.

## Before you change things

- Read [docs/DECISIONS.md](docs/DECISIONS.md). The roadmap is in
  [GitHub Issues](https://github.com/calvin-young/decal-press/issues).
- Update [docs/PROMPT_STATS.md](docs/PROMPT_STATS.md) at the end of each working session.

## Data

Tests and examples use synthetic geometry and generic names. Never commit real production or
customer data, real file paths, or fonts that can't be redistributed.

## Pull requests

Finish and test first, submit once, one logical change per PR, fill in the template including
**Requested vs. assumed**. AI-made commits end with `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
