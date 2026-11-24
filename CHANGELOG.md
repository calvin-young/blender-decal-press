# Changelog

Version history of Decal Press. Builds are GitHub pre-releases until the owner signals a full
release.

## Unreleased

- The manifest's website points to the renamed repo, blender-decal-press.

## 0.5.0 (2026-11-24)

Fixes, from a bug hunt over 8 shapes, 4 sizes (2 to 2000 mm) and 6 transforms (scale applied and
not, non-uniform, rotated, mirrored):
- Decals showed on every face of an object without a material slot (a fresh primitive, many
  imported parts), mirrored and upside down on the back. Faces with a material index past the
  last slot did the same. On a cube it didn't add at all.
- A decal added over part of another one moved the first one's UVs.
- A failed Add left a half-made decal and the faces reassigned.
- Remove left an extra slot, the emptied material and the UV map behind, and worked on the active
  object only.
- Undo brought back a decal's text but not its image.
- Small decals were blurry (a 2 mm face got a 40 px image) and the image could be slightly stretched.

Changes:
- No Resolution setting: text is drawn at 48 px/mm (two texels per 600 dpi printhead dot), at
  least 256 px on the short side, so it looks the same on a 2 mm face and a 200 mm one.
- Size: *Fill* (with Scale) or *Letter Height* in mm. The panel shows the letter height and warns
  under 2 mm.
- Decals are drawn in Solid shading (Overlays > Objects > Decals turns it off).
- The panel sits right under the material slots, lists every decal on the object, and has a
  Select Faces button per decal. Preferences: *Panel* (Material Properties or Sidebar) and
  *Sidebar Tab*.
- Notes in the panel when the mesh is shared by several objects, and when a modifier moves the
  surface under the decals.
- *Rotate 90°* is now *Other Side*.
- Faster: text is measured once and redrawn only when it changes (a color change on a 20 mm label
  went from 109 ms to 4 ms); images are packed when the file is saved.

## 0.4.0 (2026-11-10)

Renamed Decal Press; panel in the Material tab; Nunito ExtraBold; fit into the largest clear area,
oriented by the faces' straight sides; Offset, Rotation and Scale.

## 0.1.0 to 0.3.0 (2026-11-09)

Text decals on selected faces (0.1.0, as Face Label), layered and image decals (0.2.0, as Print
Decals), bundled font with fallbacks and Replace Material's background (0.3.0).
