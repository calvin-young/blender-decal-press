# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young

"""Face Label: draw text into an image and map it onto selected faces.

The label lives on its own material (Image Texture wired straight into the
Principled BSDF Base Color, which is what 3MF exporters pick up). The image is
packed into the .blend and redrawn whenever a label setting changes.
"""

import os
import re
import tempfile

import blf
import bmesh
import bpy
import imbuf
import numpy as np
from bpy.props import (BoolProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty, StringProperty)
from mathutils import Vector

IMAGE_NODE = "Face Label Image"
MAX_PIXELS = 8192  # longest image side
MEASURE_SIZE = 200  # font size used to measure the ink box

# Bold sans fonts tried in order when no font file is set.
FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)

_font_ids = {}


def _font_id(path):
    path = bpy.path.abspath(path) if path else ""
    if not path:
        path = next((p for p in FONT_CANDIDATES if os.path.isfile(p)), "")
    if not path:
        return 0  # Blender's own UI font
    if path not in _font_ids:
        fid = blf.load(path) if os.path.isfile(path) else -1
        _font_ids[path] = fid if fid != -1 else 0
    return _font_ids[path]


def _srgb(c):
    """Scene-linear to sRGB, one channel."""
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _safe_name(text):
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_.")
    return "Label_" + (name[:48] or "blank")


# ---------------------------------------------------------------------------
# Drawing

def _render_alpha(fid, text, size, width, height, x, y):
    """Draw text into an offscreen buffer and return its coverage (h x w)."""
    buf = imbuf.new((width, height))
    blf.size(fid, size)
    with blf.bind_imbuf(fid, buf):
        blf.color(fid, 1.0, 1.0, 1.0, 1.0)
        blf.position(fid, x, y, 0.0)
        blf.draw_buffer(fid, text)
    # imbuf has no pixel access from Python, so round-trip through a PNG.
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
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
    blf.size(fid, MEASURE_SIZE)
    pad = MEASURE_SIZE
    width = int(blf.dimensions(fid, text)[0]) + 2 * pad
    alpha = _render_alpha(fid, text, MEASURE_SIZE, width, 3 * pad, pad, pad)
    ys, xs = np.nonzero(alpha > 0.02)
    if not len(xs):
        return None
    return xs.min() - pad, xs.max() + 1 - pad, ys.min() - pad, ys.max() + 1 - pad


def draw_label_pixels(s, width, height):
    """RGBA float pixels (bottom row first) for label settings s."""
    bg = np.array(s.background_color, dtype=np.float32)
    fg = np.array(s.text_color, dtype=np.float32)
    alpha = np.zeros((height, width), dtype=np.float32)
    fid = _font_id(s.font_path)
    text_box = _ink_box(fid, s.text) if s.text.strip() else None
    if text_box:
        # Vertical extent includes a cap and a descender, so labels with and
        # without them get the same text size and baseline.
        ref = _ink_box(fid, "Hg")
        x0, x1 = text_box[0], text_box[1]
        y0, y1 = min(text_box[2], ref[2]), max(text_box[3], ref[3])
        margin = s.margin * min(width, height)
        scale = min((height - 2 * margin) / (y1 - y0),
                    (width - 2 * margin) / (x1 - x0))
        if scale > 0:
            x = (width - (x1 - x0) * scale) / 2 - x0 * scale
            y = (height - (y1 - y0) * scale) / 2 - y0 * scale
            alpha = _render_alpha(fid, s.text, MEASURE_SIZE * scale,
                                  width, height, x, y)
    a = alpha[..., None]
    rgba = np.empty((height, width, 4), dtype=np.float32)
    rgba[..., :3] = bg * (1 - a) + fg * a
    rgba[..., 3] = 1.0
    return rgba


def image_size(s):
    w, h = max(s.width_mm, 1e-3), max(s.height_mm, 1e-3)
    ppm = min(s.pixels_per_mm, MAX_PIXELS / max(w, h))
    return max(4, round(w * ppm)), max(4, round(h * ppm))


def update_label(mat):
    """Redraw, rename and repack the label image of mat."""
    s = mat.face_label
    width, height = image_size(s)
    name = _safe_name(s.text)
    img = s.image
    if img is None:
        img = bpy.data.images.new(name, width, height, alpha=False)
        s.image = img
    elif tuple(img.size) != (width, height):
        img.scale(width, height)
    if img.name != name:
        img.name = name
    if mat.name != name:
        mat.name = name
    img.pixels.foreach_set(draw_label_pixels(s, width, height).ravel())
    img.update()
    img.pack()
    node = mat.node_tree.nodes.get(IMAGE_NODE) if mat.node_tree else None
    if node:
        node.image = img
    mat.diffuse_color = (*s.background_color, 1.0)


def _on_change(self, context):
    if self.is_label:
        update_label(self.id_data)


# ---------------------------------------------------------------------------
# Settings stored on the label material

class FaceLabelSettings(bpy.types.PropertyGroup):
    is_label: BoolProperty(default=False)
    text: StringProperty(name="Text", default="", update=_on_change)
    text_color: FloatVectorProperty(
        name="Text", subtype="COLOR_GAMMA", size=3, min=0, max=1,
        default=(0.05, 0.05, 0.05), update=_on_change)
    background_color: FloatVectorProperty(
        name="Background", subtype="COLOR_GAMMA", size=3, min=0, max=1,
        default=(1.0, 1.0, 1.0), update=_on_change)
    font_path: StringProperty(
        name="Font", subtype="FILE_PATH", update=_on_change,
        description="TTF/OTF font file. Empty uses a bold system sans")
    margin: FloatProperty(
        name="Margin", min=0.0, max=0.45, default=0.1, subtype="FACTOR",
        update=_on_change,
        description="Space around the text, as a fraction of the face's short side")
    pixels_per_mm: FloatProperty(
        name="Resolution", min=1.0, max=100.0, default=20.0, update=_on_change,
        description="Image pixels per mm (1 Blender unit = 1 mm)")
    rotation: IntProperty(min=0, max=3, default=0)
    width_mm: FloatProperty(default=10.0)
    height_mm: FloatProperty(default=10.0)
    image: PointerProperty(type=bpy.types.Image)


def new_label_material(text, background):
    mat = bpy.data.materials.new(_safe_name(text))
    if not mat.node_tree:
        mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None)
        out = out or nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    tex = nodes.new("ShaderNodeTexImage")
    tex.name = tex.label = IMAGE_NODE
    tex.extension = "EXTEND"
    tex.location = bsdf.location + Vector((-320, 0))
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    s = mat.face_label
    s.background_color = background
    s.text = text
    return mat


def _base_color(mat):
    """sRGB base color of an untextured material, or None."""
    if mat is None or mat.face_label.is_label:
        return None
    if mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                sock = n.inputs["Base Color"]
                if sock.is_linked:
                    return None
                return tuple(_srgb(c) for c in sock.default_value[:3])
    return tuple(_srgb(c) for c in mat.diffuse_color[:3])


# ---------------------------------------------------------------------------
# UV fitting

def fit_label(obj, bm, mat_index, mat):
    """Map the faces using mat_index onto the label's 0-1 UV square.

    The image's long axis follows the longest edge, reading upright on walls
    and from above (or below) on flat faces. Stores the face size in mm.
    """
    faces = [f for f in bm.faces if f.material_index == mat_index]
    if not faces:
        return False
    mw = obj.matrix_world
    nmat = mw.to_3x3().inverted_safe().transposed()
    normal = Vector()
    for f in faces:
        normal += (nmat @ f.normal) * f.calc_area()
    if normal.length < 1e-9:
        return False
    normal.normalize()

    longest, u = -1.0, None
    for f in faces:
        for e in f.edges:
            d = mw @ e.verts[1].co - mw @ e.verts[0].co
            d -= normal * d.dot(normal)
            if d.length > longest:
                longest, u = d.length, d
    if not u or u.length < 1e-9:
        return False
    u.normalize()
    if abs(normal.z) < 0.9:
        if normal.cross(u).z < 0:
            u = -u
    elif u.x < -1e-6 or (abs(u.x) <= 1e-6 and u.y < 0):
        u = -u
    v = normal.cross(u)
    for _ in range(mat.face_label.rotation):
        u, v = v, -u

    uv_layer = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
    coords = {}
    for f in faces:
        for loop in f.loops:
            p = mw @ loop.vert.co
            coords[loop] = (p.dot(u), p.dot(v))
    us = [c[0] for c in coords.values()]
    vs = [c[1] for c in coords.values()]
    umin, vmin = min(us), min(vs)
    w, h = max(us) - umin, max(vs) - vmin
    if w < 1e-6 or h < 1e-6:
        return False
    for loop, (pu, pv) in coords.items():
        loop[uv_layer].uv = ((pu - umin) / w, (pv - vmin) / h)
    s = mat.face_label
    s.width_mm, s.height_mm = w, h
    return True


def _slot_index(obj, mat):
    for i, slot in enumerate(obj.material_slots):
        if slot.material == mat:
            return i
    obj.data.materials.append(mat)
    return len(obj.material_slots) - 1


def active_label(context):
    """The label material under the active face (Edit Mode) or active slot."""
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        return None
    mat = None
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        face = bm.faces.active
        if face is None or not face.select:
            face = next((f for f in bm.faces if f.select), None)
        if face and face.material_index < len(obj.material_slots):
            mat = obj.material_slots[face.material_index].material
    else:
        mat = obj.active_material
    return mat if mat and mat.face_label.is_label else None


def refit(obj, mat):
    """Refit and redraw every face of obj that uses mat."""
    idx = _slot_index(obj, mat)
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        ok = fit_label(obj, bm, idx, mat)
        bmesh.update_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        ok = fit_label(obj, bm, idx, mat)
        bm.to_mesh(obj.data)
        bm.free()
    if ok:
        update_label(mat)
    return ok


# ---------------------------------------------------------------------------
# Operators

class FACELABEL_OT_apply(bpy.types.Operator):
    """Put a text label on the selected faces (a new label, or the one already under the active face)"""
    bl_idname = "face_label.apply"
    bl_label = "Label Selected Faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.edit_object
        return obj is not None and obj.type == "MESH"

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        selected = [f for f in bm.faces if f.select]
        if not selected:
            self.report({"WARNING"}, "Select the faces to label")
            return {"CANCELLED"}
        mat = active_label(context)
        if mat is None:
            old = None
            if selected[0].material_index < len(obj.material_slots):
                old = obj.material_slots[selected[0].material_index].material
            background = _base_color(old) or (1.0, 1.0, 1.0)
            mat = new_label_material(context.scene.face_label_text, background)
        idx = _slot_index(obj, mat)
        bm = bmesh.from_edit_mesh(obj.data)  # slot changes can rebuild it
        for f in bm.faces:
            if f.select:
                f.material_index = idx
        mat.face_label.is_label = True
        if not refit(obj, mat):
            self.report({"WARNING"}, "Could not fit the label: faces have no area")
            return {"CANCELLED"}
        obj.active_material_index = idx
        return {"FINISHED"}


class FACELABEL_OT_rotate(bpy.types.Operator):
    """Turn the label 90 degrees on its faces"""
    bl_idname = "face_label.rotate"
    bl_label = "Rotate 90°"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_label(context) is not None

    def execute(self, context):
        mat = active_label(context)
        s = mat.face_label
        s.rotation = (s.rotation + 1) % 4
        refit(context.active_object, mat)
        return {"FINISHED"}


class FACELABEL_OT_refit(bpy.types.Operator):
    """Refit the label to its faces after editing them"""
    bl_idname = "face_label.refit"
    bl_label = "Refit"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return active_label(context) is not None

    def execute(self, context):
        refit(context.active_object, active_label(context))
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# UI: 3D Viewport sidebar, "Label" tab

class FACELABEL_PT_panel(bpy.types.Panel):
    bl_label = "Face Label"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Label"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        layout = self.layout
        mat = active_label(context)
        if mat is None:
            if context.mode != "EDIT_MESH":
                layout.label(text="Select faces in Edit Mode", icon="INFO")
                return
            layout.prop(context.scene, "face_label_text", text="")
            layout.operator(FACELABEL_OT_apply.bl_idname, icon="FONT_DATA")
            return

        s = mat.face_label
        layout.prop(s, "text", text="")
        col = layout.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(s, "text_color")
        col.prop(s, "background_color")
        col.prop(s, "margin")
        col.prop(s, "pixels_per_mm")
        col.prop(s, "font_path")
        row = layout.row(align=True)
        row.operator(FACELABEL_OT_rotate.bl_idname, icon="FILE_REFRESH")
        row.operator(FACELABEL_OT_refit.bl_idname, icon="UV")
        if context.mode == "EDIT_MESH":
            layout.operator(FACELABEL_OT_apply.bl_idname, text="Add Selection to Label")
        if s.image:
            w, h = s.image.size
            col = layout.column(align=True)
            col.label(text=s.image.name, icon="IMAGE_DATA")
            col.label(text=f"{s.width_mm:.1f} x {s.height_mm:.1f} mm, {w} x {h} px")


classes = (FaceLabelSettings, FACELABEL_OT_apply, FACELABEL_OT_rotate,
           FACELABEL_OT_refit, FACELABEL_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.face_label = PointerProperty(type=FaceLabelSettings)
    bpy.types.Scene.face_label_text = StringProperty(
        name="Label Text", default="Label",
        description="Text for the next label")


def unregister():
    del bpy.types.Scene.face_label_text
    del bpy.types.Material.face_label
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
