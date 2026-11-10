# Print Decals (working name)

A Blender add-on that puts text or an image on selected faces as a texture, for full-color 3D printing
(e.g. HP MJF 580): legible labels and logos with no embossing or engraving.

## Use

1. In Edit Mode, select the face (or coplanar faces).
2. 3D Viewport sidebar (N) → **Decal** tab → *New Decal on Selected Faces*: pick **Text** and type,
   or **Image** and pick or open one, then **Add Decal**.
3. Select a decal's face again to edit it: text, color, font, margin, resolution; for images,
   **Remove Color** makes one color transparent (tolerance and softness). Changes redraw it in place.

The decal is as tall as the face allows, or as wide when it's too long, with a margin around it.
**Rotate 90°** turns it, **Refit** remaps it after you edit the geometry, **×** removes it.

## How it works

By default a decal is a **texture layer** over the face's own material: the selected faces get a copy
of their material in which a Mix node (factor = the decal's alpha) blends the decal over the Base
Color, read through its own UV map (`UVMap Layer 1`, ...). [blender-3mf-io](https://github.com/calvin-young/blender-3mf-io)
(layered-textures branch) exports that as a layered 3MF (`multiproperties`). Netfabb can't keep
layered textures, so *Advanced → Replace Material* gives the faces an opaque material of their own
instead (the decal drawn on a background color).

Each decal is its own image (`Decal_<text>`, the name the 3MF texture gets), packed into the .blend
with its settings, so it survives saves. Image sources are packed too. Text is drawn with Blender's
own `blf` module (no PIL). The default font is set in the add-on preferences. 1 Blender unit = 1 mm.

## Status

0.2.0. Tested on Blender 5.2.3. Needs 4.4 or newer (4.2 lacks `blf.bind_imbuf`); 4.4 and 4.5 are
untested. Written by Claude (Anthropic) at Calvin Young's request.

## License

GPL-3.0-or-later.
