# AGENTS.md

Guidance for AI coding agents (and humans) working in this repository.
The human-facing overview is in [README.md](README.md).

## Project at a glance

- **What it is:** a Blender add-on that puts text or image decals on selected faces as textures,
  layered over the faces' material (layered 3MF) or replacing it, for full-color printing.
- **Status:** in development (0.4.0, 2026-11-10). Tested on Blender 5.2.3 only.
- **Runs in:** Blender 4.5+ as an extension (`decal_press/blender_manifest.toml`).

## Setup, test, package

- **Install for development:** `ln -s "$PWD/decal_press" ~/.config/blender/<version>/extensions/user_default/decal_press`,
  then enable "Decal Press" in Preferences > Add-ons.
- **Shape test:** `blender -b --factory-startup --python tests/blender/shapes.py` renders decals on
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
tests/blender/shapes.py   synthetic-shape renders
docs/                     DECISIONS.md, PROMPT_STATS.md, images for the README
```

## Conventions

- 1 Blender unit = 1 mm.
- A decal's settings live on its Image (`Image.decal_press`), so they travel with the packed image.
- The layered node pattern (Mix RGBA factor = texture alpha, A = below, B = decal, UV Map node,
  extension CLIP) is what blender-3mf-io's `layers.py` recognizes. Change both together.
- Property updates: content changes find the fit again (`_on_content`), placement only rewrites
  UVs (`_on_place`), looks only redraw (`_on_change`).
- SPDX `GPL-3.0-or-later` header on every source file.
- UI/UX matters more to the maintainer than code style.

## Where knowledge lives

Work moves between sessions and assistants, so anything a future session needs is written into this
repo and pushed. Current state and next steps go here, the reasons behind decisions go in
`docs/DECISIONS.md`, bugs and planned features go in GitHub Issues.

## State and next steps

- 0.1.0 to 0.3.0 (2026-11-09): text decals, then layered/image decals, bundled font, fallbacks.
- 0.4.0 (2026-11-10): renamed Decal Press; panel moved to the Material tab; Nunito ExtraBold; fit
  into the largest clear area, orientation from the faces' straight sides; Offset/Rotation/Scale.
- **Builds:** every build gets a tag, a GitHub pre-release with the zip, and a new download link on
  the Workbench row (see ai-context, topics/workstation.md). Attach the zip at the top of the reply.
- Open: the maintainer's test on real parts; a decal 3MF in Magics/SmartStream and on the 580;
  Blender 4.5 (issue); curved selections (issue).

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
