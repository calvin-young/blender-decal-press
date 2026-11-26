# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young

"""Decal Press: put text or an image on selected faces as a texture.

By default a decal is a texture layer over the face's own material: a copy of
that material gets a Mix node (factor = the decal's alpha) in front of the
Principled BSDF Base Color, reading the decal through its own UV map. That is
the pattern blender-3mf-io exports as a layered 3MF (multiproperties). The
"Replace Material" mode gives the faces an opaque material of their own
instead, for tools that can't read layered 3MFs.

Each decal is its own image, packed into the .blend. Its settings live on that
image and the image is redrawn whenever a setting changes.
"""

import atexit
import math
import os
import re
import tempfile

import blf
import bmesh
import bpy
import gpu
import imbuf
import numpy as np
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy.props import (BoolProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)
from mathutils import Vector

MAX_PIXELS = 8192  # longest image side
MAX_TOTAL_PIXELS = 16_000_000  # whole text image, about 256 MB while drawing
# Full-color and Dual Tone MJF print color at the printhead's 600 dpi (0.042 mm),
# and ink bleed blurs it to about one PA 12 grain (55-60 um), so no print shows
# detail finer than that. Two texels per printhead dot is the most a decal ever needs.
PRINT_PIXELS_PER_MM = 48.0  # about 1200 dpi
MIN_TEXT_PIXELS = 256  # short side of a text image, so tiny decals stay sharp on screen
SOFT_PIXELS_PER_MM = 12.0  # half the printhead's 600 dpi: an image below this prints soft
LEGIBLE_MM = 2.0  # smallest letter height the owner aims for on printed parts
UV_MAP_LIMIT = 8  # Blender's limit per mesh
MEASURE_SIZE = 200  # font size used to measure the ink box
BASE_KEY = "decal_press_base"  # material custom property: the material it was copied from
MADE_KEY = "decal_press_made"  # material custom property: made by Decal Press

# Bundled default: Nunito ExtraBold (SIL Open Font License, see fonts/OFL.txt),
# a static instance of the Nunito variable font at weight 800.
BUNDLED_FONT = os.path.join(os.path.dirname(__file__), "fonts", "Nunito-ExtraBold.ttf")

# Bold sans system fonts, tried when the fonts above fail to load.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

_font_ids = {}  # path -> blf font id, or None when it didn't load or draw
_drawn = {}  # decal image session_uid -> settings its pixels were drawn with
font_warnings = {}  # decal image pointer -> message, shown in the panel


def _prefs():
    addon = bpy.context.preferences.addons.get(__package__)
    return addon.preferences if addon else None


def _load_font(path):
    """blf id of a font that loads and draws, or None."""
    if path not in _font_ids:
        fid = blf.load(path) if os.path.isfile(path) else -1
        ok = fid != -1 and _ink_box(fid, "Hg") is not None
        _font_ids[path] = fid if ok else None
    return _font_ids[path]


def _font_id(path, decal=None):
    """The first usable font: decal's own, the preferences', bundled, system.

    Falls back to Blender's UI font, which is always there. Records a warning
    for decal when a font it asked for couldn't be used.
    """
    prefs = _prefs()
    wanted = [bpy.path.abspath(p) for p in
              (path, prefs.default_font if prefs else "") if p]
    if decal is not None:
        font_warnings.pop(decal, None)
    for p in wanted + [BUNDLED_FONT, *FONT_CANDIDATES]:
        fid = _load_font(p)
        if fid is not None:
            return fid
        if p in wanted and decal is not None and decal not in font_warnings:
            font_warnings[decal] = f"Couldn't use font {os.path.basename(p)}, using a fallback"
    return 0


def _srgb(c):
    """Scene-linear to sRGB, one channel."""
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _safe_name(text):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_.")
    return "Decal_" + (name[:48] or "blank")


def decal_name(s):
    if s.kind == "IMAGE":
        src = s.source
        return _safe_name(os.path.splitext(src.name)[0] if src else "image")
    return _safe_name(s.text)


# ---------------------------------------------------------------------------
# Drawing

_coverage = {}  # (font id, text, size, width, height, x, y) -> last coverage drawn
_ink_boxes = {}  # (font id, text) -> ink box


def _render_alpha(fid, text, size, width, height, x, y):
    """Coverage (h x w) of text drawn into an image, cached for redraws that keep it."""
    key = (fid, text, round(size, 4), width, height, round(x, 3), round(y, 3))
    if key not in _coverage:
        if len(_coverage) > 8:
            _coverage.clear()
        _coverage[key] = _draw_alpha(fid, text, size, width, height, x, y)
    return _coverage[key].copy()


def _draw_alpha(fid, text, size, width, height, x, y):
    """Draw text into an offscreen buffer and return its coverage (h x w)."""
    buf = imbuf.new((width, height))
    blf.size(fid, size)
    with blf.bind_imbuf(fid, buf):
        blf.color(fid, 1.0, 1.0, 1.0, 1.0)
        blf.position(fid, x, y, 0.0)
        blf.draw_buffer(fid, text)
    # imbuf has no pixel access from Python, so round-trip through a file:
    # BMP, which keeps alpha and writes 15x faster than PNG.
    fd, path = tempfile.mkstemp(suffix=".bmp")
    os.close(fd)
    try:
        buf.file_type = "BMP"
        imbuf.write(buf, filepath=path)
        img = bpy.data.images.load(path, check_existing=False)
        try:
            px = np.empty(width * height * 4, dtype=np.float32)
            img.pixels.foreach_get(px)
        finally:
            bpy.data.images.remove(img)
    finally:
        os.remove(path)
    return px.reshape(height, width, 4)[..., 3]


def _ink_box(fid, text):
    """Ink extents (x0, x1, y0, y1) relative to the pen origin at MEASURE_SIZE."""
    key = (fid, text)
    if key not in _ink_boxes:
        if len(_ink_boxes) > 256:
            _ink_boxes.clear()
        _ink_boxes[key] = _measure_ink(fid, text)
    return _ink_boxes[key]


def _measure_ink(fid, text):
    blf.size(fid, MEASURE_SIZE)
    pad = MEASURE_SIZE
    width = int(blf.dimensions(fid, text)[0]) + 2 * pad
    alpha = _draw_alpha(fid, text, MEASURE_SIZE, width, 3 * pad, pad, pad)
    ys, xs = np.nonzero(alpha > 0.02)
    if not len(xs):
        return None
    return xs.min() - pad, xs.max() + 1 - pad, ys.min() - pad, ys.max() + 1 - pad


def text_pixels_per_mm(w_mm, h_mm):
    """Image resolution for a text decal of w_mm x h_mm.

    At least print resolution, more for small decals so their short side gets
    MIN_TEXT_PIXELS, within the size limits. So the same text looks the same
    on a 2 mm face and a 200 mm one.
    """
    ppm = max(PRINT_PIXELS_PER_MM, MIN_TEXT_PIXELS / min(w_mm, h_mm))
    return min(ppm, MAX_PIXELS / max(w_mm, h_mm), math.sqrt(MAX_TOTAL_PIXELS / (w_mm * h_mm)))


def _text_pixels(s):
    w_mm, h_mm = max(s.width_mm, 1e-3), max(s.height_mm, 1e-3)
    ppm = text_pixels_per_mm(w_mm, h_mm)
    # Keep the image's aspect ratio exactly the decal's, or the text stretches.
    if w_mm >= h_mm:
        height = max(4, round(h_mm * ppm))
        width = max(4, round(height * w_mm / h_mm))
    else:
        width = max(4, round(w_mm * ppm))
        height = max(4, round(width * h_mm / w_mm))
    alpha = np.zeros((height, width), dtype=np.float32)
    fid = _font_id(s.font_path, s.id_data.as_pointer())
    text_box = _ink_box(fid, s.text) if s.text.strip() else None
    if text_box:
        # Vertical extent includes a cap and a descender, so decals with and
        # without them get the same text size and baseline.
        ref = _ink_box(fid, "Hg")
        x0, x1 = text_box[0], text_box[1]
        y0, y1 = min(text_box[2], ref[2]), max(text_box[3], ref[3])
        margin = _pad_mm(s) * height / h_mm
        scale = min((height - 2 * margin) / (y1 - y0),
                    (width - 2 * margin) / (x1 - x0))
        if scale > 0:
            x = (width - (x1 - x0) * scale) / 2 - x0 * scale
            y = (height - (y1 - y0) * scale) / 2 - y0 * scale
            alpha = _render_alpha(fid, s.text, MEASURE_SIZE * scale,
                                  width, height, x, y)
            # Capital letter height on the part.
            s.letter_mm = ref[3] * scale * h_mm / height
    if not text_box:
        s.letter_mm = 0.0
    rgba = np.empty((height, width, 4), dtype=np.float32)
    rgba[..., :3] = np.array(s.text_color, dtype=np.float32)
    rgba[..., 3] = alpha
    return rgba


def _pad_mm(s):
    """Margin around the content in mm, as fitted (or from the margin, before a fit)."""
    if s.pad_mm >= 0:
        return s.pad_mm
    return s.margin * min(max(s.width_mm, 1e-3), max(s.height_mm, 1e-3))


def _image_pixels(s):
    """The source image, keyed, centred on a transparent canvas of the face's shape."""
    src = s.source
    if src is None or src.size[0] == 0 or src.size[1] == 0:
        return np.zeros((4, 4, 4), dtype=np.float32)
    w, h = src.size
    px = np.empty(w * h * 4, dtype=np.float32)
    src.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    if s.use_key:
        dist = np.linalg.norm(px[..., :3] - np.array(s.key_color, dtype=np.float32),
                              axis=-1) / np.sqrt(3.0)
        soft = max(s.key_softness, 1e-4)
        px[..., 3] *= np.clip((dist - s.key_tolerance) / soft, 0.0, 1.0)

    # Pad (never resample) to the decal's aspect ratio, keeping the margin.
    w_mm, h_mm = max(s.width_mm, 1e-3), max(s.height_mm, 1e-3)
    margin = _pad_mm(s)
    mm_per_px = min((w_mm - 2 * margin) / w, (h_mm - 2 * margin) / h)
    if mm_per_px <= 0:
        return np.zeros((4, 4, 4), dtype=np.float32)
    cw, ch = max(w, round(w_mm / mm_per_px)), max(h, round(h_mm / mm_per_px))
    step = -(-max(cw, ch) // MAX_PIXELS)  # thin the source if the canvas is too big
    if step > 1:
        px = px[::step, ::step]
        h, w = px.shape[:2]
        cw, ch = cw // step, ch // step
    canvas = np.zeros((ch, cw, 4), dtype=np.float32)
    ox, oy = (cw - w) // 2, (ch - h) // 2
    canvas[oy:oy + h, ox:ox + w] = px
    return canvas


def decal_pixels(s):
    """RGBA float pixels (bottom row first) for decal settings s."""
    rgba = _image_pixels(s) if s.kind == "IMAGE" else _text_pixels(s)
    if s.mode == "REPLACE":
        a = rgba[..., 3:4]
        rgba[..., :3] = np.array(s.background_color, dtype=np.float32) * (1 - a) + rgba[..., :3] * a
        rgba[..., 3] = 1.0
        # Replace textures extend their edge pixels past the decal: keep them background.
        rgba[[0, -1], :, :3] = background = np.array(s.background_color, dtype=np.float32)
        rgba[:, [0, -1], :3] = background
    return rgba


def _drawn_with(s):
    """Everything that changes a decal's pixels."""
    return (s.kind, s.mode, s.text, tuple(s.text_color), tuple(s.background_color),
            s.font_path, round(s.margin, 6), s.source.name if s.source else "", s.use_key,
            tuple(s.key_color), round(s.key_tolerance, 6), round(s.key_softness, 6),
            round(s.width_mm, 6), round(s.height_mm, 6))


def update_decal(img):
    """Redraw and rename decal image img. It's packed when the file is saved."""
    s = img.decal_press
    _drawn[img.session_uid] = _drawn_with(s)
    if s.kind == "IMAGE" and s.source and s.source.source == "FILE" and not s.source.packed_file:
        s.source.pack()  # keep the original with the .blend, for later edits
    rgba = decal_pixels(s)
    height, width = rgba.shape[:2]
    if tuple(img.size) != (width, height):
        # A blank image of the new size: scale() would resample pixels about to be replaced.
        img.source = "GENERATED"
        img.generated_width, img.generated_height = width, height
    name = decal_name(s)
    if re.sub(r"\.\d{3}$", "", img.name) != name:
        img.name = name
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    for mat in decal_materials(img):
        if s.mode == "REPLACE":
            mat.diffuse_color = (*(_lin(c) for c in s.background_color), 1.0)
            mat.name = img.name
        else:
            mat.name = "+".join([_base_name(mat)] + [n.image.name for n in decal_nodes(mat)])


def _base_name(mat):
    base = mat.get(BASE_KEY)
    return base.name if isinstance(base, bpy.types.Material) else "Material"


def _lin(c):
    """sRGB to scene-linear, one channel."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _on_change(self, context):
    """Redraw only: nothing that changes where the decal goes."""
    if self.is_decal:
        update_decal(self.id_data)


def _on_content(self, context):
    """The content's shape may have changed: find its fit rectangle again."""
    if self.is_decal and not refit(self.id_data, search=True):
        update_decal(self.id_data)


def _on_place(self, context):
    if self.is_decal:
        refit(self.id_data, search=False, redraw=False)


def _on_scale(self, context):
    if self.is_decal:
        refit(self.id_data, search=False)


def _not_decal(self, img):
    return not img.decal_press.is_decal


# ---------------------------------------------------------------------------
# Settings

KINDS = [("TEXT", "Text", "A line of text", "FONT_DATA", 0),
         ("IMAGE", "Image", "An image, optionally with one color keyed out", "IMAGE_DATA", 1)]
FITS = [("CLEAR", "Clear Area",
         "Fit the decal into the largest area inside the faces", 0),
        ("BOUNDS", "Whole Selection",
         "Fit the decal to the rectangle around the faces", 1)]
SIZES = [("FILL", "Fill", "As big as the faces allow, then Scale", 0),
         ("HEIGHT", "Letter Height", "Capital letters this tall, in mm", 1)]
MODES = [("LAYER", "Layer over Material",
          "Blend the decal over the face's own material (layered 3MF; not for Netfabb)", 0),
         ("REPLACE", "Replace Material",
          "Give the faces an opaque material with the decal on a background color", 1)]


class DecalSettings(bpy.types.PropertyGroup):
    """Stored on the decal's image."""
    is_decal: BoolProperty(default=False)
    kind: EnumProperty(items=KINDS, default="TEXT")
    mode: EnumProperty(items=MODES, default="LAYER")
    text: StringProperty(name="Text", default="", update=_on_content)
    text_color: FloatVectorProperty(
        name="Color", subtype="COLOR_GAMMA", size=3, min=0, max=1,
        default=(0.0, 0.0, 0.0), update=_on_change)
    background_color: FloatVectorProperty(
        name="Background", subtype="COLOR_GAMMA", size=3, min=0, max=1,
        default=(1.0, 1.0, 1.0), update=_on_change)
    font_path: StringProperty(
        name="Font", subtype="FILE_PATH", update=_on_content,
        description="TTF/OTF font file. Empty uses the default font from the add-on preferences")
    margin: FloatProperty(
        name="Margin", min=0.0, max=0.45, default=0.1, subtype="FACTOR",
        update=_on_scale,
        description="Space around the decal, as a fraction of the face's short side")
    source: PointerProperty(name="Image", type=bpy.types.Image, poll=_not_decal,
                            update=_on_content)
    use_key: BoolProperty(name="Remove Color", default=False, update=_on_change,
                          description="Make one color of the image transparent")
    key_color: FloatVectorProperty(
        name="Color", subtype="COLOR_GAMMA", size=3, min=0, max=1,
        default=(1.0, 1.0, 1.0), update=_on_change)
    key_tolerance: FloatProperty(
        name="Tolerance", min=0.0, max=1.0, default=0.1, subtype="FACTOR",
        update=_on_change, description="How far a color may be from it and still be removed")
    key_softness: FloatProperty(
        name="Softness", min=0.0, max=1.0, default=0.05, subtype="FACTOR",
        update=_on_change, description="Width of the fade between removed and kept colors")
    fit: EnumProperty(items=FITS, default="CLEAR", update=_on_content, name="Fit")
    offset: FloatVectorProperty(
        name="Offset", size=2, subtype="XYZ", default=(0.0, 0.0), update=_on_place,
        description="Move the decal from its fitted position, in mm along its own axes")
    angle: FloatProperty(
        name="Rotation", subtype="ANGLE", default=0.0, soft_min=-math.pi, soft_max=math.pi,
        update=_on_place, description="Turn the decal on its faces")
    scale: FloatProperty(
        name="Scale", min=0.05, max=20.0, soft_max=4.0, default=1.0, update=_on_scale,
        description="Size relative to the fitted size")
    size_mode: EnumProperty(items=SIZES, default="FILL", name="Size", update=_on_scale)
    letter_height: FloatProperty(
        name="Letter Height", min=0.1, soft_max=50.0, default=5.0, precision=2,
        update=_on_scale, description="Height of the capital letters on the part, in mm")
    rotation: IntProperty(min=0, max=3, default=0)  # quarter turns of the fit frame
    fit_rect: FloatVectorProperty(size=4)  # (u0, v0, u1, v1) in mm in the fit frame
    width_mm: FloatProperty(default=10.0)
    pad_mm: FloatProperty(default=-1.0)  # margin around the content in mm; -1: not fitted yet
    off_faces: BoolProperty(default=False)  # moved entirely off its faces
    letter_mm: FloatProperty(default=0.0)  # capital letter height of a text decal
    height_mm: FloatProperty(default=10.0)
    uv_map: StringProperty()
    show_expanded: BoolProperty(default=True)


class NewDecalSettings(bpy.types.PropertyGroup):
    """What the next Add Decal creates (on the scene)."""
    kind: EnumProperty(items=KINDS, default="TEXT")
    mode: EnumProperty(items=MODES, default="LAYER")
    text: StringProperty(name="Text", default="Label")
    image: PointerProperty(name="Image", type=bpy.types.Image, poll=_not_decal)


class DecalPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_font: StringProperty(
        name="Default Font", subtype="FILE_PATH",
        description="Font for text decals that don't set their own. "
                    "Empty uses the bundled Nunito ExtraBold")
    panel_location: EnumProperty(
        name="Panel", default="PROPERTIES", update=lambda self, ctx: _register_panels(),
        items=[("PROPERTIES", "Material Properties", "Under the material slots in the "
                "Properties editor's Material tab", 0),
               ("SIDEBAR", "Sidebar", "In a tab of the 3D Viewport's sidebar (N)", 1)])
    sidebar_tab: StringProperty(
        name="Sidebar Tab", default="Decal", update=lambda self, ctx: _register_panels(),
        description="Sidebar tab for the panel. Give several add-ons the same name to share a tab")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "default_font")
        layout.prop(self, "panel_location", expand=True)
        row = layout.row()
        row.active = self.panel_location == "SIDEBAR"
        row.prop(self, "sidebar_tab")


# ---------------------------------------------------------------------------
# Materials

def _principled(mat):
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        out = out or nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return bsdf


def _new_material(name):
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    return mat


def decal_nodes(mat):
    """Image Texture nodes of mat that show a decal."""
    if mat is None or mat.node_tree is None:
        return []
    return [n for n in mat.node_tree.nodes
            if n.type == "TEX_IMAGE" and n.image and n.image.decal_press.is_decal]


def decal_materials(img):
    return [m for m in bpy.data.materials if any(n.image == img for n in decal_nodes(m))]


def _uv_maps_in_use(obj):
    """UV maps read by any material on obj (decal layers and the user's own)."""
    return {n.uv_map for slot in obj.material_slots
            if slot.material and slot.material.node_tree
            for n in slot.material.node_tree.nodes if n.type == "UVMAP"}


def _free_layer_uv(obj):
    """A UV map name no material on obj reads, so a new decal can't move another's."""
    used = _uv_maps_in_use(obj)
    k = 1
    while f"UVMap Layer {k}" in used:
        k += 1
    return f"UVMap Layer {k}"


def layered_copy(base, img, uv_map):
    """A copy of base with img blended over its Base Color through uv_map."""
    if base is None:
        mat = _new_material("Material")
    else:
        mat = base.copy()
        mat[BASE_KEY] = mat.get(BASE_KEY) or base
    mat[MADE_KEY] = True
    mat.name = f"{(base.name if base else 'Material')}+{img.name}"
    nt = mat.node_tree
    bsdf = _principled(mat)
    sock = bsdf.inputs["Base Color"]
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MIX"
    if sock.is_linked:
        nt.links.new(sock.links[0].from_socket, mix.inputs[6])
    else:
        mix.inputs[6].default_value = sock.default_value[:]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "CLIP"
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = uv_map
    nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], mix.inputs[7])
    nt.links.new(tex.outputs["Alpha"], mix.inputs[0])
    nt.links.new(mix.outputs[2], sock)
    x, y = bsdf.location.x, bsdf.location.y - 360 - 300 * len(decal_nodes(mat))
    mix.location = (x - 220, y)
    tex.location = (x - 520, y)
    uvn.location = (x - 720, y)
    return mat


def replace_material(img):
    mat = _new_material(img.name)
    mat[MADE_KEY] = True
    nt = mat.node_tree
    bsdf = _principled(mat)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "EXTEND"
    tex.location = bsdf.location + Vector((-320, 0))
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def remove_from_material(mat, img):
    """Unhook img's layer from mat. True when no decal is left in mat."""
    nt = mat.node_tree
    for tex in [n for n in decal_nodes(mat) if n.image == img]:
        for link in list(tex.outputs["Color"].links):
            mix = link.to_node
            if mix.type == "MIX":
                below = mix.inputs[6]
                targets = [l.to_socket for l in mix.outputs[2].links]
                for t in targets:
                    if below.is_linked:
                        nt.links.new(below.links[0].from_socket, t)
                    else:
                        t.default_value = below.default_value
                nt.nodes.remove(mix)
        uvn = tex.inputs["Vector"].links[0].from_node if tex.inputs["Vector"].is_linked else None
        nt.nodes.remove(tex)
        if uvn and uvn.type == "UVMAP" and not uvn.outputs[0].is_linked:
            nt.nodes.remove(uvn)
    return not decal_nodes(mat)


def _base_color(mat):
    """sRGB background for a Replace Material decal on faces using mat, or None.

    The Principled Base Color when it's a plain color, else the material's
    viewport (diffuse) color.
    """
    if mat is None:
        return None
    if mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                sock = n.inputs["Base Color"]
                if not sock.is_linked:
                    return tuple(_srgb(c) for c in sock.default_value[:3])
                break
    return tuple(_srgb(c) for c in mat.diffuse_color[:3])


# ---------------------------------------------------------------------------
# UV fitting

def _slot_index(obj, mat):
    for i, slot in enumerate(obj.material_slots):
        if slot.material == mat:
            return i
    obj.data.materials.append(mat)
    return len(obj.material_slots) - 1


def _prepare_slots(obj):
    """Give every face a real material slot before decal slots are added.

    Faces of an object with no slots, or with a material index past the last
    slot, show the last slot's material. A decal slot appended after them
    would then show on all of those faces.
    """
    if not obj.material_slots:
        obj.data.materials.append(None)
    last = len(obj.material_slots) - 1
    bm = bmesh.from_edit_mesh(obj.data)
    changed = False
    for f in bm.faces:
        if f.material_index > last:
            f.material_index = last
            changed = True
    if changed:
        bmesh.update_edit_mesh(obj.data)


def _face_indices(obj):
    """Material index of every face, from Edit Mode data when editing."""
    if obj.mode == "EDIT":
        return [f.material_index for f in bmesh.from_edit_mesh(obj.data).faces]
    return [p.material_index for p in obj.data.polygons]


def _move_faces(obj, old, new):
    """Move the faces in slot old to slot new."""
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        for f in bm.faces:
            if f.material_index == old:
                f.material_index = new
        bmesh.update_edit_mesh(obj.data)
    else:
        for p in obj.data.polygons:
            if p.material_index == old:
                p.material_index = new


def _drop_unused_decal_slots(obj):
    """Remove slots holding a decal material that no face uses any more."""
    used = set(_face_indices(obj))
    for i in reversed(range(len(obj.material_slots))):
        mat = obj.material_slots[i].material
        if i in used or mat is None or not (decal_nodes(mat) or MADE_KEY in mat
                                             or BASE_KEY in mat):
            continue
        obj.data.materials.pop(index=i)
        if obj.mode == "EDIT":
            # pop() renumbers faces in Object Mode only.
            bm = bmesh.from_edit_mesh(obj.data)
            for f in bm.faces:
                if f.material_index > i:
                    f.material_index -= 1
            bmesh.update_edit_mesh(obj.data)
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def _hull(points):
    """Convex hull of 2D points (monotone chain), counter-clockwise."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) > 1 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                    - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]
    return half(pts) + half(reversed(pts))


def _hull_candidates(xy):
    """Rows of xy (N x 2) that can be on the convex hull.

    Drops the points strictly inside the octagon of the extreme points
    (Akl-Toussaint), so the Python hull only sees the outline of dense meshes.
    """
    if len(xy) < 16:
        return xy
    x, y = xy[:, 0], xy[:, 1]
    order = [np.argmin(x), np.argmin(x + y), np.argmin(y), np.argmax(x - y),
             np.argmax(x), np.argmax(x + y), np.argmax(y), np.argmin(x - y)]
    poly = [xy[i] for k, i in enumerate(order) if k == 0 or i != order[k - 1]]
    inside = np.ones(len(xy), dtype=bool)
    for p0, p1 in zip(poly, poly[1:] + poly[:1]):
        cross = (p1[0] - p0[0]) * (y - p0[1]) - (p1[1] - p0[1]) * (x - p0[0])
        inside &= cross > 1e-12
    return xy[~inside]


def _frame_axes(normal, points, quarter_turns):
    """Image axes (u, v) on the plane of normal for world points.

    The frame is the smallest rectangle around the points, or the
    world-aligned one when it's about as small (round or square shapes).
    u runs along its long side, or the side closer to world horizontal when
    it's nearly square, and reads upright on walls and from above (or
    below) on flat faces.
    """
    a = normal.orthogonal().normalized()
    b = normal.cross(a)
    xy = np.asarray(points, dtype=np.float64) @ np.array([a[:], b[:]]).T
    hull = _hull([tuple(p) for p in _hull_candidates(xy)])
    if abs(normal.z) < 0.9:
        world = Vector((0, 0, 1)).cross(normal)
    else:
        world = Vector((1, 0, 0)) - normal * normal.x
    world.normalize()

    def extent(d):
        e = (d.dot(a), d.dot(b))
        xs = [x * e[0] + y * e[1] for x, y in hull]
        ys = [y * e[0] - x * e[1] for x, y in hull]
        return max(xs) - min(xs), max(ys) - min(ys)

    edges = [a * (x1 - x0) + b * (y1 - y0)
             for (x0, y0), (x1, y1) in zip(hull, hull[1:] + hull[:1])]
    edges = [e for e in edges if e.length > 1e-9]
    perimeter = sum(e.length for e in edges)
    best, d = None, world
    for e in edges:
        w, h = extent(e.normalized())
        if best is None or w * h < best:
            best, d = w * h, e.normalized()
    # Follow the shape only when it has real straight sides along (or across)
    # that direction; organic or round outlines stay world-aligned.
    straight = sum(e.length for e in edges
                   if abs(e.normalized().dot(d)) > 0.9998 or abs(e.normalized().dot(d)) < 0.02)
    w, h = extent(world)
    if best is None or w * h <= best * 1.02 or straight < 0.3 * perimeter:
        d = world
    w, h = extent(d)
    p = normal.cross(d)
    if max(w, h) < 1.25 * min(w, h):
        u = d if abs(d.dot(world)) >= abs(p.dot(world)) else p
    else:
        u = d if w >= h else p
    if abs(normal.z) < 0.9:
        if normal.cross(u).z < 0:
            u = -u
    elif u.x < -1e-6 or (abs(u.x) <= 1e-6 and u.y < 0):
        u = -u
    v = normal.cross(u)
    for _ in range(quarter_turns):
        u, v = v, -u
    return u, v


def _clear_rect(tris, width, height, aspect):
    """Largest rectangle (u0, v0, u1, v1) inside 2D triangles for content of aspect.

    Rasterizes the triangles and picks the covered rectangle that fits the
    content biggest, then the biggest of those. Coordinates start at 0.
    """
    cell = min(max(width, height) / 96, min(width, height) / 24)
    cell = max(cell, math.sqrt(width * height / 20000))
    nu, nv = max(1, math.ceil(width / cell)), max(1, math.ceil(height / cell))
    gu = (np.arange(nu) + 0.5) * cell
    gv = (np.arange(nv) + 0.5) * cell
    mask = np.zeros((nv, nu), dtype=bool)
    tri = np.asarray(tris, dtype=np.float64).reshape(-1, 3, 2)
    i0 = np.clip(np.floor(tri[..., 0].min(1) / cell - 0.5), 0, nu).astype(int)
    i1 = np.clip(np.ceil(tri[..., 0].max(1) / cell - 0.5) + 1, 0, nu).astype(int)
    j0 = np.clip(np.floor(tri[..., 1].min(1) / cell - 0.5), 0, nv).astype(int)
    j1 = np.clip(np.ceil(tri[..., 1].max(1) / cell - 0.5) + 1, 0, nv).astype(int)

    def inside(t, x, y):
        (ax, ay), (bx, by), (cx, cy) = (t[..., k, :].T for k in range(3)) if t.ndim == 3 else t
        if t.ndim == 3:
            ax, ay, bx, by, cx, cy = (c[:, None] for c in (ax, ay, bx, by, cx, cy))
        d1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        d2 = (cx - bx) * (y - by) - (cy - by) * (x - bx)
        d3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx)
        return (((d1 >= 0) & (d2 >= 0) & (d3 >= 0))
                | ((d1 <= 0) & (d2 <= 0) & (d3 <= 0)))

    # Small triangles (dense meshes) all at once, over a k x k block of cells each.
    k = 4
    small = np.maximum(i1 - i0, j1 - j0) <= k
    if small.any():
        di, dj = np.meshgrid(np.arange(k), np.arange(k))
        ii = i0[small, None] + di.ravel()
        jj = j0[small, None] + dj.ravel()
        hit = (ii < i1[small, None]) & (jj < j1[small, None]) & inside(
            tri[small], (ii + 0.5) * cell, (jj + 0.5) * cell)
        mask[jj[hit], ii[hit]] = True
    for t in np.flatnonzero(~small):
        x, y = gu[None, i0[t]:i1[t]], gv[j0[t]:j1[t], None]
        mask[j0[t]:j1[t], i0[t]:i1[t]] |= inside(tri[t], x, y)
    if mask.all():
        return 0.0, 0.0, width, height

    # Every maximal rectangle, one histogram per row.
    best, rect = (-1.0, 0), None
    heights = np.zeros(nu, dtype=int)
    for r in range(nv):
        heights = np.where(mask[r], heights + 1, 0)
        hs = heights.tolist() + [0]
        stack = []
        for i, h in enumerate(hs):
            start = i
            while stack and stack[-1][1] >= h:
                st, sh = stack.pop()
                if sh:
                    w = i - st
                    key = (min(w / aspect, sh), w * sh)
                    if key > best:
                        best, rect = key, (st, i, r + 1 - sh, r + 1)
                start = st
            stack.append((start, h))
    if rect is None:
        return 0.0, 0.0, width, height
    c0, c1, r0, r1 = rect
    # Cell centres are inside; the edges may be half a cell out.
    u0, u1 = (c0 + 0.5) * cell, min(width, (c1 - 0.5) * cell)
    v0, v1 = (r0 + 0.5) * cell, min(height, (r1 - 0.5) * cell)
    if u1 - u0 < cell:
        u0, u1 = c0 * cell, min(width, c1 * cell)
    if v1 - v0 < cell:
        v0, v1 = r0 * cell, min(height, r1 * cell)
    return u0, v0, u1, v1


def _text_metrics(s):
    """(width, height, cap height) of the text's ink at MEASURE_SIZE, or None.

    The height spans a capital and a descender, as the text is drawn.
    """
    if s.kind != "TEXT" or not s.text.strip():
        return None
    fid = _font_id(s.font_path, s.id_data.as_pointer())
    box, ref = _ink_box(fid, s.text), _ink_box(fid, "Hg")
    if not box or not ref:
        return None
    return box[1] - box[0], max(box[3], ref[3]) - min(box[2], ref[2]), ref[3]


def _content_aspect(s):
    """Width / height of what the decal shows."""
    if s.kind == "IMAGE":
        src = s.source
        return src.size[0] / src.size[1] if src and src.size[1] else 1.0
    m = _text_metrics(s)
    return m[0] / m[1] if m else 1.0


def _letter_box(s):
    """Decal (w, h, margin) in mm for text whose capitals are s.letter_height tall."""
    m = _text_metrics(s)
    if m is None:
        return None
    ink_w, ink_h, cap = m
    h_ink = s.letter_height * ink_h / cap
    w_ink = h_ink * ink_w / ink_h
    pad = s.margin * min(w_ink, h_ink) / (1 - 2 * s.margin)
    return w_ink + 2 * pad, h_ink + 2 * pad, pad


def _content_box(s, avail_w, avail_h):
    """Decal (w, h, margin) in mm: the content as big as fits in avail_w x avail_h.

    The margin is a fraction of the available short side. The decal hugs the
    content, so its image spends every pixel on the text or picture.
    """
    if s.kind == "TEXT":
        m = _text_metrics(s)
        if m is None:
            return None
        cw, ch = m[0], m[1]
    else:
        src = s.source
        if src is None or not src.size[0] or not src.size[1]:
            return None
        cw, ch = src.size
    pad = s.margin * min(avail_w, avail_h)
    k = min((avail_w - 2 * pad) / cw, (avail_h - 2 * pad) / ch)
    if k <= 0:
        return None
    return cw * k + 2 * pad, ch * k + 2 * pad, pad


def _mesh_array(me, kind, n):
    """Mesh data as a numpy array, read the fastest way that sees the current mesh.

    In Object Mode the attribute API is 10-80x faster than the legacy polygon,
    loop and vertex collections. In Edit Mode mesh.attributes shows the edit
    mesh's layers instead, so read the synced mesh through the legacy ones.
    """
    editing = me.is_editmode
    if kind == "material_index":
        out = np.zeros(n, dtype=np.int32)
        attr = None if editing else me.attributes.get("material_index")
        if editing:
            me.polygons.foreach_get("material_index", out)
        elif attr is not None:
            attr.data.foreach_get("value", out)
    elif kind == "corner_vert":
        out = np.empty(n, dtype=np.int32)
        if editing:
            me.loops.foreach_get("vertex_index", out)
        else:
            me.attributes[".corner_vert"].data.foreach_get("value", out)
    else:  # position
        out = np.empty(n * 3, dtype=np.float32)
        if editing:
            me.vertices.foreach_get("co", out)
        else:
            me.attributes["position"].data.foreach_get("vector", out)
    return out


def _decal_loops(obj, img):
    """(faces, loops, loop vertices) of obj's mesh where img shows, as arrays, or None."""
    me = obj.data
    slots = [i for i, slot in enumerate(obj.material_slots)
             if slot.material and any(n.image == img for n in decal_nodes(slot.material))]
    nf, nl = len(me.polygons), len(me.loops)
    if not slots or not nf:
        return None
    mat = _mesh_array(me, "material_index", nf)
    faces = np.flatnonzero(np.isin(mat, slots))
    if not len(faces):
        return None
    start = np.empty(nf, dtype=np.int32)
    me.polygons.foreach_get("loop_start", start)
    total = np.diff(np.append(start, nl))
    counts = total[faces]
    ends = np.cumsum(counts)
    offsets = np.arange(ends[-1]) - np.repeat(ends - counts, counts)
    loops = np.repeat(start[faces], counts) + offsets
    loop_vert = _mesh_array(me, "corner_vert", nl)
    # Each loop's successor within its face, for edge-based normals.
    nxt = np.arange(1, len(loops) + 1)
    nxt[ends - 1] = ends - counts
    return faces, loops, loop_vert[loops], nxt


def fit_decal(obj, img, search=True):
    """UVs (loops, uv) mapping the faces of obj that show img onto it, or None.

    Reads obj.data (synced from Edit Mode by the caller). The decal sits in its
    fit rectangle, found again when search is set (or never found yet), then
    moved, turned and sized by its placement settings. Stores the decal's size.
    """
    s = img.decal_press
    found = _decal_loops(obj, img)
    if found is None:
        return None
    faces, loops, verts, nxt = found
    me = obj.data
    co = _mesh_array(me, "position", len(me.vertices))
    mw = np.array(obj.matrix_world, dtype=np.float64)
    world = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]

    # Sum of p x p_next over every face's edges: twice the area-weighted normal.
    # A mirroring transform reverses the winding, so flip it back.
    corners = world[verts]
    normal = Vector(np.cross(corners, corners[nxt]).sum(axis=0))
    if np.linalg.det(mw[:3, :3]) < 0:
        normal = -normal
    if normal.length < 1e-9:
        return None
    normal.normalize()

    points = world[np.unique(verts)]
    u, v = _frame_axes(normal, points, s.rotation)
    uv_axes = np.array([u[:], v[:]]).T
    pu, pv = (points @ uv_axes).T
    umin, vmin = pu.min(), pv.min()
    width, height = pu.max() - umin, pv.max() - vmin
    if width < 1e-6 or height < 1e-6:
        return None

    if search or s.fit_rect[2] <= s.fit_rect[0]:
        if s.fit == "CLEAR":
            me.calc_loop_triangles()
            nt = len(me.loop_triangles)
            tri_verts = np.empty(nt * 3, dtype=np.int32)
            tri_face = np.empty(nt, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri_verts)
            me.loop_triangles.foreach_get("polygon_index", tri_face)
            keep = np.isin(tri_face, faces)
            tris = world[tri_verts.reshape(-1, 3)[keep]] @ uv_axes - (umin, vmin)
            s.fit_rect = _clear_rect(tris, width, height, _content_aspect(s))
        else:
            s.fit_rect = (0.0, 0.0, width, height)
    u0, v0, u1, v1 = s.fit_rect
    cu = umin + (u0 + u1) / 2 + s.offset[0]
    cv = vmin + (v0 + v1) / 2 + s.offset[1]
    avail_w, avail_h = max((u1 - u0) * s.scale, 1e-3), max((v1 - v0) * s.scale, 1e-3)
    if s.kind == "TEXT" and s.size_mode == "HEIGHT":
        box = _letter_box(s)
    else:
        box = _content_box(s, avail_w, avail_h)
    if box:
        dw, dh, s.pad_mm = box
    else:
        dw, dh, s.pad_mm = avail_w, avail_h, s.margin * min(avail_w, avail_h)
    ca, sa = math.cos(-s.angle), math.sin(-s.angle)
    # Off its faces when its turned bounds miss the faces' bounds entirely.
    ex = abs(dw * ca) + abs(dh * sa)
    ey = abs(dw * sa) + abs(dh * ca)
    s.off_faces = bool(abs(cu - umin - width / 2) >= (width + ex) / 2
                       or abs(cv - vmin - height / 2) >= (height + ey) / 2)

    x, y = (corners @ uv_axes - (cu, cv)).T
    uv = np.empty((len(loops), 2), dtype=np.float32)
    uv[:, 0] = (x * ca - y * sa) / dw + 0.5
    uv[:, 1] = (x * sa + y * ca) / dh + 0.5
    s.width_mm, s.height_mm = dw, dh
    return faces, loops, uv


def decal_objects(img):
    """Mesh objects with a material that shows img."""
    mats = set(decal_materials(img))
    return [o for o in bpy.data.objects if o.type == "MESH"
            and any(slot.material in mats for slot in o.material_slots)]


def refit(img, search=True, redraw=True, objects=None):
    """Refit decal img on its objects and redraw it."""
    s = img.decal_press
    ok = False
    for obj in objects or decal_objects(img):
        editing = obj.mode == "EDIT"
        if editing:
            obj.update_from_editmode()  # read the edited mesh with numpy
        fitted = fit_decal(obj, img, search)
        if fitted is None:
            continue
        ok = True
        faces, loops, uv = fitted
        if not s.uv_map:
            active = obj.data.uv_layers.active
            s.uv_map = active.name if active else "UVMap"
        if editing:
            bm = bmesh.from_edit_mesh(obj.data)
            layer = bm.loops.layers.uv.get(s.uv_map) or bm.loops.layers.uv.new(s.uv_map)
            bm.faces.ensure_lookup_table()
            k = 0
            for fi in faces.tolist():
                for loop in bm.faces[fi].loops:
                    loop[layer].uv = uv[k]
                    k += 1
            bmesh.update_edit_mesh(obj.data)
        else:
            me = obj.data
            if s.uv_map not in me.uv_layers:
                me.uv_layers.new(name=s.uv_map)
            attr = me.attributes[s.uv_map]  # 30x faster than uv_layers[...].data
            data = np.empty(len(me.loops) * 2, dtype=np.float32)
            attr.data.foreach_get("vector", data)
            data = data.reshape(-1, 2)
            data[loops] = uv
            attr.data.foreach_set("vector", data.ravel())
            me.update()
    if ok and redraw:
        update_decal(img)
    return ok


def active_material(context):
    """The material under the active face (Edit Mode) or in the active slot."""
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    if obj.mode != "EDIT":
        return obj.active_material
    bm = bmesh.from_edit_mesh(obj.data)
    face = bm.faces.active
    if face is None or not face.select:
        face = next((f for f in bm.faces if f.select), None)
    if face and face.material_index < len(obj.material_slots):
        return obj.material_slots[face.material_index].material
    return None


def active_decals(context):
    return [n.image for n in decal_nodes(active_material(context))]


def object_decals(obj):
    """Every decal shown on obj, in slot order."""
    found = []
    for slot in obj.material_slots if obj and obj.type == "MESH" else ():
        for n in decal_nodes(slot.material):
            if n.image not in found:
                found.append(n.image)
    return found


# ---------------------------------------------------------------------------
# Operators

class DECALPRESS_OT_add(bpy.types.Operator):
    """Put a new text or image decal on the selected faces"""
    bl_idname = "decal_press.add"
    bl_label = "Add Decal"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        new = context.scene.decal_press_new
        if new.kind == "IMAGE" and new.image is None:
            self.report({"WARNING"}, "Pick or open an image first")
            return {"CANCELLED"}
        # Every object in Edit Mode with selected faces gets its own decal.
        objects = [o for o in context.objects_in_mode_unique_data if o.type == "MESH"
                   and any(f.select for f in bmesh.from_edit_mesh(o.data).faces)]
        if not objects:
            self.report({"WARNING"}, "Select the faces for the decal")
            return {"CANCELLED"}
        problems = [p for p in (self._check(o, new) for o in objects) if p]
        if problems:
            self.report({"WARNING"}, "; ".join(problems))
            return {"CANCELLED"}
        for obj in objects:
            self._add(obj, new)
        return {"FINISHED"}

    @staticmethod
    def _check(obj, new):
        """What stops a decal going on obj's selected faces, or None."""
        name = f"{obj.name}: " if len(bpy.context.objects_in_mode_unique_data) > 1 else ""
        selected = [f for f in bmesh.from_edit_mesh(obj.data).faces if f.select]
        nmat = obj.matrix_world.to_3x3().inverted_safe().transposed()
        normal, total = Vector(), 0.0
        for f in selected:
            n = (nmat @ f.normal) * f.calc_area()
            normal += n
            total += n.length
        if total < 1e-12:
            return name + "the selected faces have no area"
        if normal.length < 0.2 * total:
            return (name + "the selected faces point in all directions: "
                    "select faces on one side of the part")
        if new.mode == "LAYER":
            uv_map = _free_layer_uv(obj)
            if uv_map not in obj.data.uv_layers and len(obj.data.uv_layers) >= UV_MAP_LIMIT:
                return (name + f"the mesh already has {UV_MAP_LIMIT} UV maps, Blender's "
                        "limit: remove a decal or a UV map first")
        return None

    @staticmethod
    def _add(obj, new):
        """Put a new decal on obj's selected faces. _check passed."""
        _prepare_slots(obj)
        bm = bmesh.from_edit_mesh(obj.data)  # slot changes can rebuild it
        selected = [f for f in bm.faces if f.select]
        slots = obj.material_slots
        bases = {f.index: slots[f.material_index].material for f in selected}

        img = bpy.data.images.new("Decal", 4, 4, alpha=True)
        img.alpha_mode = "STRAIGHT"
        s = img.decal_press
        s.kind, s.mode = new.kind, new.mode
        if new.kind == "TEXT":
            s.text = new.text
        else:
            s.source = new.image
        first = next(iter(bases.values()))
        s.background_color = _base_color(first) or (1.0, 1.0, 1.0)
        img.name = decal_name(s)

        if new.mode == "LAYER":
            s.uv_map = _free_layer_uv(obj)
            copies = {}
            for base in set(bases.values()):
                copies[base] = layered_copy(base, img, s.uv_map)
            targets = {fi: copies[b] for fi, b in bases.items()}
        else:
            mat = replace_material(img)
            if first:
                mat[BASE_KEY] = first.get(BASE_KEY) or first
            targets = {fi: mat for fi in bases}
        index = {m: _slot_index(obj, m) for m in set(targets.values())}

        bm = bmesh.from_edit_mesh(obj.data)  # slot changes can rebuild it
        bm.faces.ensure_lookup_table()
        for fi, mat in targets.items():
            bm.faces[fi].material_index = index[mat]
        bmesh.update_edit_mesh(obj.data)
        _drop_unused_decal_slots(obj)  # a decal moved onto every face of another one
        s.is_decal = True
        refit(img, objects=[obj])
        obj.active_material_index = next(i for i, slot in enumerate(obj.material_slots)
                                         if slot.material in targets.values())


class _DecalOperator:
    bl_options = {"REGISTER", "UNDO"}
    image: StringProperty()

    def decal(self, context):
        img = bpy.data.images.get(self.image)
        return img if img and img.decal_press.is_decal else None


class DECALPRESS_OT_rotate(_DecalOperator, bpy.types.Operator):
    """Fit the decal along the other side of its faces"""
    bl_idname = "decal_press.rotate"
    bl_label = "Other Side"

    def execute(self, context):
        img = self.decal(context)
        if img is None:
            return {"CANCELLED"}
        img.decal_press.rotation = (img.decal_press.rotation + 1) % 4
        refit(img)
        return {"FINISHED"}


class DECALPRESS_OT_select(_DecalOperator, bpy.types.Operator):
    """Select the faces this decal is on, in Edit Mode"""
    bl_idname = "decal_press.select"
    bl_label = "Select Faces"

    def execute(self, context):
        img = self.decal(context)
        obj = context.active_object
        if img is None or obj is None or obj.type != "MESH":
            return {"CANCELLED"}
        slots = {i for i, slot in enumerate(obj.material_slots)
                 if slot.material and any(n.image == img for n in decal_nodes(slot.material))}
        if obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")
        context.tool_settings.mesh_select_mode = (False, False, True)
        bm = bmesh.from_edit_mesh(obj.data)
        for f in bm.faces:
            f.select_set(f.material_index in slots)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
        return {"FINISHED"}


class DECALPRESS_OT_refit(_DecalOperator, bpy.types.Operator):
    """Find the decal's place on its faces again, after editing them"""
    bl_idname = "decal_press.refit"
    bl_label = "Refit"

    def execute(self, context):
        img = self.decal(context)
        if img is None:
            return {"CANCELLED"}
        refit(img)
        return {"FINISHED"}


class DECALPRESS_OT_remove(_DecalOperator, bpy.types.Operator):
    """Remove the decal. Faces go back to their original material where there is one"""
    bl_idname = "decal_press.remove"
    bl_label = "Remove Decal"

    def execute(self, context):
        img = self.decal(context)
        if img is None:
            return {"CANCELLED"}
        s = img.decal_press
        objects = decal_objects(img)
        for mat in decal_materials(img):
            base = mat.get(BASE_KEY)
            base = base if isinstance(base, bpy.types.Material) else None
            if s.mode == "REPLACE" or remove_from_material(mat, img):
                # Nothing left on these faces: give them back their own material.
                for obj in objects:
                    for i, slot in enumerate(obj.material_slots):
                        if slot.material == mat:
                            _move_faces(obj, i, _slot_index(obj, base))
            else:
                mat.name = "+".join([_base_name(mat)] + [n.image.name for n in decal_nodes(mat)])
        for obj in objects:
            _drop_unused_decal_slots(obj)
            uv = obj.data.uv_layers.get(s.uv_map)
            if (uv and re.fullmatch(r"UVMap Layer \d+", uv.name)
                    and uv.name not in _uv_maps_in_use(obj)):
                obj.data.uv_layers.remove(uv)
        for mat in decal_materials(img):
            if mat.users == 0:
                bpy.data.materials.remove(mat)
        if img.users == 0:
            bpy.data.images.remove(img)
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Solid shading: draw the decals over their faces, as they will print

SHAPE_MODIFIERS = {"SUBSURF", "MULTIRES", "DISPLACE", "SMOOTH", "LAPLACIANSMOOTH",
                   "CORRECTIVE_SMOOTH", "SHRINKWRAP", "SIMPLE_DEFORM", "CAST", "WAVE",
                   "REMESH", "SOLIDIFY"}
_shader = None
_batches = {}  # object name -> [(image, batch)]
_draw_handle = None


def _overlay_shader():
    global _shader
    if _shader is None:
        iface = gpu.types.GPUStageInterfaceInfo("decal_press_iface")
        iface.smooth("VEC2", "uvInterp")
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant("MAT4", "viewProjection")
        info.push_constant("MAT4", "objectMatrix")
        info.sampler(0, "FLOAT_2D", "image")
        info.vertex_in(0, "VEC3", "pos")
        info.vertex_in(1, "VEC2", "uv")
        info.vertex_out(iface)
        info.fragment_out(0, "VEC4", "fragColor")
        # Pulled a little toward the viewer so it wins against its own face.
        info.vertex_source(
            "void main() {"
            "  uvInterp = uv;"
            "  gl_Position = viewProjection * objectMatrix * vec4(pos, 1.0);"
            "  gl_Position.z -= 0.00005 * gl_Position.w;"
            "}")
        # Layer decals clip outside the image (extension CLIP), as they print.
        info.fragment_source(
            "void main() {"
            "  if (any(lessThan(uvInterp, vec2(0.0))) || any(greaterThan(uvInterp, vec2(1.0))))"
            "    discard;"
            "  vec4 c = texture(image, uvInterp);"
            "  if (c.a < 0.004) discard;"
            "  fragColor = c;"
            "}")
        _shader = gpu.shader.create_from_info(info)
    return _shader


def _object_batches(obj, depsgraph):
    if obj.name in _batches:
        return _batches[obj.name]
    out = []
    decals = object_decals(obj)
    if decals:
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        try:
            me.calc_loop_triangles()
            n = len(me.loop_triangles)
            tri_loops = np.empty(n * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("loops", tri_loops)
            tri_mat = np.empty(n, dtype=np.int32)
            me.loop_triangles.foreach_get("material_index", tri_mat)
            loop_vert = np.empty(len(me.loops), dtype=np.int32)
            me.loops.foreach_get("vertex_index", loop_vert)
            co = np.empty(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            for img in decals:
                layer = me.uv_layers.get(img.decal_press.uv_map)
                slots = [i for i, slot in enumerate(obj.material_slots)
                         if slot.material and any(nd.image == img
                                                  for nd in decal_nodes(slot.material))]
                if layer is None or not slots:
                    continue
                loops = tri_loops.reshape(-1, 3)[np.isin(tri_mat, slots)].ravel()
                if not len(loops):
                    continue
                uv = np.empty(len(me.loops) * 2, dtype=np.float32)
                layer.data.foreach_get("uv", uv)
                out.append((img, batch_for_shader(
                    _overlay_shader(), "TRIS",
                    {"pos": co[loop_vert[loops]], "uv": uv.reshape(-1, 2)[loops]})))
        finally:
            ev.to_mesh_clear()
    _batches[obj.name] = out
    return out


def _draw_solid():
    context = bpy.context
    space = context.space_data
    scene = context.scene
    if (space is None or space.shading.type != "SOLID"
            or not getattr(scene, "decal_press_show_solid", True)
            or not space.overlay.show_overlays):
        return
    depsgraph = context.evaluated_depsgraph_get()
    shader = _overlay_shader()
    vp = context.region_data.perspective_matrix
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.depth_mask_set(False)
    gpu.state.blend_set("ALPHA")
    try:
        for obj in context.visible_objects:
            if obj.type != "MESH":
                continue
            for img, batch in _object_batches(obj, depsgraph):
                shader.bind()
                shader.uniform_float("viewProjection", vp)
                shader.uniform_float("objectMatrix", obj.matrix_world)
                shader.uniform_sampler("image", gpu.texture.from_image(img))
                batch.draw(shader)
    finally:
        gpu.state.blend_set("NONE")
        gpu.state.depth_test_set("NONE")


@persistent
def _on_depsgraph(scene, depsgraph):
    for update in depsgraph.updates:
        if isinstance(update.id, bpy.types.Object):
            if update.is_updated_geometry or update.is_updated_shading:
                _batches.pop(update.id.name, None)
        elif isinstance(update.id, (bpy.types.Mesh, bpy.types.Material, bpy.types.Image)):
            _batches.clear()
            return


@persistent
def _on_load(*_):
    # Opening a file frees the fonts loaded with blf.load: their ids are stale.
    _font_ids.clear()
    _ink_boxes.clear()
    _coverage.clear()
    _batches.clear()
    _drawn.clear()
    font_warnings.clear()


@persistent
def _on_save(*_):
    """Pack decals drawn since the last save, so the .blend carries them."""
    for img in bpy.data.images:
        if img.decal_press.is_decal and (img.is_dirty or not img.packed_file):
            img.pack()
        src = img.decal_press.source if img.decal_press.is_decal else None
        if src and not src.packed_file and (src.source == "GENERATED" or src.is_dirty):
            src.pack()  # an image made or painted in Blender would be lost on reload


@persistent
def _on_undo(*_):
    """Undo brings back a decal's settings but not its pixels: redraw what changed."""
    for img in bpy.data.images:
        s = img.decal_press
        if s.is_decal and _drawn.get(img.session_uid, _drawn_with(s)) != _drawn_with(s):
            update_decal(img)
    _batches.clear()


def _free_gpu():
    # GPU batches still held when Blender quits show up as unfreed memory.
    global _shader
    _batches.clear()
    _shader = None


atexit.register(_free_gpu)


def _draw_overlay_toggle(self, context):
    self.layout.prop(context.scene, "decal_press_show_solid")


# ---------------------------------------------------------------------------
# UI

def _draw_decal(layout, img, on_face=False):
    s = img.decal_press
    box = layout.box()
    row = box.row(align=True)
    row.prop(s, "show_expanded", text="", emboss=False,
             icon="DISCLOSURE_TRI_DOWN" if s.show_expanded else "DISCLOSURE_TRI_RIGHT")
    if s.kind == "TEXT":
        row.prop(s, "text", text="", icon="FONT_DATA")
    else:
        row.label(text=img.name, icon="IMAGE_DATA")
    row.operator(DECALPRESS_OT_select.bl_idname, text="", icon="RESTRICT_SELECT_OFF",
                 emboss=False).image = img.name
    row.operator(DECALPRESS_OT_remove.bl_idname, text="", icon="X", emboss=False).image = img.name
    if not s.show_expanded:
        return
    col = box.column(align=True)
    col.use_property_split = True
    col.use_property_decorate = False
    if s.kind == "TEXT":
        col.prop(s, "text_color")
        prefs = _prefs()
        default = os.path.basename(prefs.default_font) if prefs and prefs.default_font else ""
        try:
            col.prop(s, "font_path", placeholder=default or "Nunito ExtraBold (bundled)")
        except TypeError:  # no placeholders before Blender 5.x (untested there)
            col.prop(s, "font_path")
        warning = font_warnings.get(img.as_pointer())
        if warning:
            col.label(text=warning, icon="ERROR")
    else:
        col.template_ID(s, "source", open="image.open")
        col.prop(s, "use_key")
        sub = col.column(align=True)
        sub.active = s.use_key
        sub.prop(s, "key_color")
        sub.prop(s, "key_tolerance")
        sub.prop(s, "key_softness")
    col.prop(s, "margin")
    if s.mode == "REPLACE":
        col.prop(s, "background_color")

    col.separator()
    col.prop(s, "fit")
    row = col.row(align=True)
    row.operator(DECALPRESS_OT_rotate.bl_idname, icon="FILE_REFRESH").image = img.name
    row.operator(DECALPRESS_OT_refit.bl_idname, icon="UV").image = img.name
    col.separator()
    if s.kind == "TEXT":
        col.row().prop(s, "size_mode", expand=True)
    if s.kind == "TEXT" and s.size_mode == "HEIGHT":
        col.prop(s, "letter_height")
    else:
        col.prop(s, "scale")
    col.prop(s, "offset")
    col.prop(s, "angle")

    info = box.column(align=True)
    if s.kind == "TEXT" and s.letter_mm > 0:
        info.label(text=f"Letters {s.letter_mm:.1f} mm tall, decal "
                        f"{s.width_mm:.1f} x {s.height_mm:.1f} mm")
        if s.letter_mm < LEGIBLE_MM:
            info.label(text=f"Letters under {LEGIBLE_MM:g} mm may not print legibly",
                       icon="ERROR")
    else:
        w, h = img.size
        info.label(text=f"{s.width_mm:.1f} x {s.height_mm:.1f} mm, {w} x {h} px")
        ppm = w / max(s.width_mm, 1e-6)
        if s.kind == "IMAGE" and ppm < SOFT_PIXELS_PER_MM:
            info.label(text=f"{ppm:.1f} px per mm: may print soft (the printer resolves "
                            f"about 24)", icon="ERROR")
    if s.off_faces:
        info.label(text="Moved off its faces: it won't show. Reset Offset", icon="ERROR")
    u0, v0, u1, v1 = s.fit_rect
    if s.width_mm > (u1 - u0) * 1.01 + 1e-6 or s.height_mm > (v1 - v0) * 1.01 + 1e-6:
        info.label(text="Bigger than the faces' clear area: may be cut off", icon="INFO")


class _DecalPanel:
    bl_label = "Decal Press"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        decals = object_decals(obj)
        under = set(active_decals(context)) if context.mode == "EDIT_MESH" else set()
        for img in sorted(decals, key=lambda i: i not in under):
            _draw_decal(layout, img, img in under)
        if decals:
            if obj.data.users > 1:
                layout.label(text=f"This mesh is shared by {obj.data.users} objects: "
                                  "the decals show on all of them", icon="INFO")
            if any(m.type in SHAPE_MODIFIERS and m.show_viewport for m in obj.modifiers):
                layout.label(text="Modifiers move the surface under the decals: "
                                  "apply them for exact placement", icon="INFO")

        if context.mode != "EDIT_MESH":
            layout.label(text="Select faces in Edit Mode to add a decal", icon="INFO")
            return
        new = context.scene.decal_press_new
        col = layout.column()
        col.label(text="New Decal on Selected Faces")
        col.row().prop(new, "kind", expand=True)
        if new.kind == "TEXT":
            col.prop(new, "text", text="")
        else:
            col.template_ID(new, "image", open="image.open")
        col.operator(DECALPRESS_OT_add.bl_idname, icon="ADD")
        header, body = layout.panel("decal_press_advanced", default_closed=True)
        header.label(text="Advanced")
        if body:
            body.prop(new, "mode", text="")


class DECALPRESS_PT_material(_DecalPanel, bpy.types.Panel):
    """Under the material slots, for EEVEE and Workbench"""
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_parent_id = "EEVEE_MATERIAL_PT_context_material"


class DECALPRESS_PT_material_cycles(_DecalPanel, bpy.types.Panel):
    """Under the material slots, for Cycles"""
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"
    bl_parent_id = "CYCLES_PT_context_material"


class DECALPRESS_PT_sidebar(_DecalPanel, bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Decal"


PANELS = (DECALPRESS_PT_material, DECALPRESS_PT_material_cycles, DECALPRESS_PT_sidebar)


def _register_panels():
    """Register the panel where the preferences say."""
    for cls in PANELS:
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
    prefs = _prefs()
    if prefs and prefs.panel_location == "SIDEBAR":
        DECALPRESS_PT_sidebar.bl_category = prefs.sidebar_tab.strip() or "Decal"
        bpy.utils.register_class(DECALPRESS_PT_sidebar)
        return
    for cls in (DECALPRESS_PT_material, DECALPRESS_PT_material_cycles):
        try:
            bpy.utils.register_class(cls)
        except RuntimeError:
            pass  # Cycles turned off: its slot panel isn't there


classes = (DecalSettings, NewDecalSettings, DecalPreferences, DECALPRESS_OT_add,
           DECALPRESS_OT_rotate, DECALPRESS_OT_select, DECALPRESS_OT_refit,
           DECALPRESS_OT_remove)


def register():
    global _draw_handle
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Image.decal_press = PointerProperty(type=DecalSettings)
    bpy.types.Scene.decal_press_new = PointerProperty(type=NewDecalSettings)
    bpy.types.Scene.decal_press_show_solid = BoolProperty(
        name="Decals", default=True,
        description="Show Decal Press decals in Solid shading, as they will print")
    _register_panels()
    bpy.types.VIEW3D_PT_overlay_object.append(_draw_overlay_toggle)
    _draw_handle = bpy.types.SpaceView3D.draw_handler_add(_draw_solid, (), "WINDOW", "POST_VIEW")
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.undo_post.append(_on_undo)
    bpy.app.handlers.save_pre.append(_on_save)
    bpy.app.handlers.redo_post.append(_on_undo)


def unregister():
    global _draw_handle
    bpy.app.handlers.save_pre.remove(_on_save)
    bpy.app.handlers.redo_post.remove(_on_undo)
    bpy.app.handlers.undo_post.remove(_on_undo)
    bpy.app.handlers.load_post.remove(_on_load)
    bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, "WINDOW")
        _draw_handle = None
    bpy.types.VIEW3D_PT_overlay_object.remove(_draw_overlay_toggle)
    _free_gpu()
    for cls in PANELS:
        if cls.is_registered:
            bpy.utils.unregister_class(cls)
    del bpy.types.Scene.decal_press_show_solid
    del bpy.types.Scene.decal_press_new
    del bpy.types.Image.decal_press
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
