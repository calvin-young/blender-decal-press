# Face Label

A Blender add-on that puts a text label on selected faces as a texture, for full-color 3D printing
(e.g. HP MJF 580): legible text with no embossing or engraving.

## Use

1. In Edit Mode, select the face (or coplanar faces) to label.
2. 3D Viewport sidebar (N) → **Label** tab: type the text, click **Label Selected Faces**.
3. Edit the text, colors, margin or resolution at any time: the image is redrawn in place.

The text is as tall as the face allows, or as wide when it's too long, with a margin around it.
**Rotate 90°** turns it on the face; **Refit** remaps it after you edit the geometry.

## How it works

Each label is its own material (`Label_<text>`) with an Image Texture wired straight into the
Principled BSDF Base Color, which 3MF exporters write as the face texture (`Label_<text>.png`).
The image matches the face's aspect ratio, its background defaults to the face's previous color,
and it's packed into the .blend so it survives saves. Text is drawn with Blender's own `blf`
module (no PIL). 1 Blender unit = 1 mm.

## Status

0.1.0. Tested on Blender 5.2.3. Needs 4.4 or newer (4.2 lacks `blf.bind_imbuf`); 4.4 and 4.5 are
untested. Written by Claude (Anthropic) at Calvin Young's request.

## License

GPL-3.0-or-later.
