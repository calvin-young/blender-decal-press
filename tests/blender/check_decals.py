# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young
"""Checks that decals land where they should, on many shapes, sizes and transforms.

blender -b --factory-startup --python tests/blender/check_decals.py

Each case selects faces, adds a text decal and checks:
- only the selected faces show the decal (nothing on the back of the part);
- the decal reads the right way round (not mirrored) and upright on walls;
- the decal fits on its faces;
- the image isn't stretched (pixel aspect = mm aspect);
- the letters have enough pixels to be legible.
Prints one line per case and a summary; exits with status 1 if anything fails.
"""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
bpy.ops.wm.read_factory_settings(use_empty=True)
import decal_press as dp  # noqa: E402

dp.register()
scene = bpy.context.scene
FAILS = []


def body_material():
    m = bpy.data.materials.new("Body")
    if not m.node_tree:
        m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.35, 0.45, 1)
    return m


def clear():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for item in list(coll):
            coll.remove(item)


def build(shape, size):
    """A mesh object of about size mm, and a test that picks its front faces (local space)."""
    if shape == "cube":
        bpy.ops.mesh.primitive_cube_add(size=size)
        pick = lambda f: f.normal.y < -0.9
    elif shape == "cube_top":
        bpy.ops.mesh.primitive_cube_add(size=size)
        pick = lambda f: f.normal.z > 0.9
    elif shape == "plate":  # thin label plate
        bpy.ops.mesh.primitive_cube_add(size=1)
        bpy.context.object.data.transform(Matrix.Diagonal((size, size * 0.4, size * 0.05, 1)))
        pick = lambda f: f.normal.z > 0.9
    elif shape == "cylinder_cap":
        bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, depth=size / 3, vertices=48)
        pick = lambda f: f.normal.z > 0.9
    elif shape == "cylinder_side":
        bpy.ops.mesh.primitive_cylinder_add(radius=size / 2, depth=size, vertices=48)
        pick = lambda f: abs(f.normal.z) < 0.1 and f.normal.y < -0.8
    elif shape == "dense_cube":  # triangulated and subdivided, like an imported part
        bpy.ops.mesh.primitive_cube_add(size=size)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.subdivide(number_cuts=7)
        bpy.ops.mesh.quads_convert_to_tris()
        bpy.ops.object.mode_set(mode="OBJECT")
        pick = lambda f: f.normal.y < -0.9
    elif shape == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=size / 2)
        pick = lambda f: f.normal.y < -0.8
    elif shape == "suzanne":
        bpy.ops.mesh.primitive_monkey_add(size=size)
        pick = lambda f: f.normal.y < -0.5
    else:
        raise ValueError(shape)
    return bpy.context.object, pick


def add_decal(obj, pick, text, kind="TEXT"):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    selected = set()
    for f in bm.faces:
        f.select = pick(f)
        if f.select:
            selected.add(f.index)
    bmesh.update_edit_mesh(obj.data)
    new = bpy.context.scene.decal_press_new
    new.kind = kind
    new.text = text
    result = bpy.ops.decal_press.add()
    bpy.ops.object.mode_set(mode="OBJECT")
    decals = [i for i in bpy.data.images if i.decal_press.is_decal]
    return result, (decals[-1] if decals else None), selected


def check(name, obj, img, selected, result):
    problems = []
    if result != {"FINISHED"} or img is None:
        return [f"add returned {result}"]
    s = img.decal_press
    me = obj.data
    slots = {i for i, slot in enumerate(obj.material_slots)
             if slot.material and any(n.image == img for n in dp.decal_nodes(slot.material))}
    shown = {p.index for p in me.polygons if p.material_index in slots}
    if shown != selected:
        problems.append(f"decal on {len(shown)} faces, {len(selected)} selected "
                        f"({len(shown - selected)} extra)")

    mw = obj.matrix_world
    nmat = mw.to_3x3().inverted_safe().transposed()
    flip = -1.0 if mw.to_3x3().determinant() < 0 else 1.0
    uv = me.uv_layers.get(s.uv_map)
    if uv is None:
        return problems + [f"no UV map {s.uv_map!r}"]
    mirrored = upside_down = 0
    inside = outside = 0
    for p in me.polygons:
        if p.index not in selected or len(p.loop_indices) < 3:
            continue
        li = list(p.loop_indices)
        pts = [mw @ me.vertices[me.loops[i].vertex_index].co for i in li[:3]]
        uvs = [Vector(uv.data[i].uv) for i in li[:3]]
        n = (nmat @ p.normal).normalized()
        e1, e2 = pts[1] - pts[0], pts[2] - pts[0]
        d1, d2 = uvs[1] - uvs[0], uvs[2] - uvs[0]
        area_world = e1.cross(e2).dot(n)
        area_uv = d1.x * d2.y - d1.y * d2.x
        if abs(area_world) > 1e-9 and abs(area_uv) > 1e-12:
            if (area_world > 0) != (area_uv > 0):
                mirrored += 1
            # Direction of +v (image up) in world space, from the UV gradient.
            det = d1.x * d2.y - d1.y * d2.x
            up = (e1 * (-d2.x) + e2 * d1.x) / det  # world direction where v grows, u constant
            if abs(n.z) < 0.7 and up.normalized().z < -0.1:
                upside_down += 1
        for i in li:
            u, v = uv.data[i].uv
            if -1e-4 <= u <= 1 + 1e-4 and -1e-4 <= v <= 1 + 1e-4:
                inside += 1
            else:
                outside += 1
    if outside:
        problems.append(f"{outside} UVs outside the image (readers repeat the texture there)")
    if mirrored:
        problems.append(f"mirrored on {mirrored} faces")
    if upside_down:
        problems.append(f"upside down on {upside_down} faces")

    # Fit: the decal is no bigger than the faces it sits on.
    w_px, h_px = img.size
    if s.height_mm <= 0 or s.width_mm <= 0:
        problems.append("zero size")
    else:
        x0, y0, x1, y1 = s.canvas
        aspect_mm = (x1 - x0) / (y1 - y0)
        aspect_px = w_px / h_px
        if abs(aspect_px / aspect_mm - 1) > 0.03:
            problems.append(f"stretched: {aspect_mm:.3f} mm aspect vs {aspect_px:.3f} px")
    world_pts = [mw @ me.vertices[v].co for p in me.polygons if p.index in selected
                 for v in p.vertices]
    lo = Vector([min(p[i] for p in world_pts) for i in range(3)])
    hi = Vector([max(p[i] for p in world_pts) for i in range(3)])
    span = (hi - lo).length
    if max(s.width_mm, s.height_mm) > span * 1.05:
        problems.append(f"decal {s.width_mm:.2f} mm wider than the faces ({span:.2f} mm)")

    # Sharpness: print resolution, unless the image size limits stop it.
    canvas = (s.canvas[0], s.canvas[1], s.canvas[2], s.canvas[3])
    ppm = h_px / max(canvas[3] - canvas[1], 1e-9)
    want = min(dp.PRINT_PIXELS_PER_MM, dp._canvas_ppm(canvas))
    if s.text.strip() and ppm < 0.97 * want:
        problems.append(f"only {ppm:.1f} px per mm (print resolution is {want:.0f})")
    info = (f"{s.width_mm:8.2f} x {s.height_mm:7.2f} mm  {w_px:5d} x {h_px:4d} px  "
            f"{len(selected):4d} faces  uv in/out {inside}/{outside}")
    return problems, info


SHAPES = ["cube", "cube_top", "plate", "cylinder_cap", "cylinder_side", "dense_cube",
          "sphere", "suzanne"]
SIZES = [2, 20, 200, 2000]
TRANSFORMS = {
    "applied": None,
    "scale 0.1": dict(scale=(0.1, 0.1, 0.1)),
    "scale 10": dict(scale=(10, 10, 10)),
    "scale 2,1,0.5": dict(scale=(2, 1, 0.5)),
    "rotated": dict(rotation=(0.3, -0.5, 0.9)),
    "mirror x": dict(scale=(-1, 1, 1)),
}


def run_case(shape, size, tname, transform, material, text):
    clear()
    obj, pick = build(shape, size)
    if material:
        obj.data.materials.append(body_material())
    if transform:
        obj.scale = transform.get("scale", (1, 1, 1))
        obj.rotation_euler = transform.get("rotation", (0, 0, 0))
        bpy.context.view_layer.update()
    name = f"{shape:13s} {size:5d} mm  {tname:13s} {'mat' if material else 'no mat'}  {text!r}"
    try:
        result, img, selected = add_decal(obj, pick, text)
        out = check(name, obj, img, selected, result)
    except Exception as e:  # noqa: BLE001
        out = ([f"exception {type(e).__name__}: {e}"], "")
    problems, info = out if isinstance(out, tuple) else (out, "")
    status = "ok  " if not problems else "FAIL"
    print(f"{status} {name}  {info}  {'; '.join(problems)}")
    if problems:
        FAILS.append((name, problems))


ONLY = os.environ.get("ONLY")
for shape in SHAPES:
    if ONLY and shape not in ONLY.split(","):
        continue
    for size in SIZES:
        run_case(shape, size, "applied", None, True, "Label 42")
    run_case(shape, 20, "applied", None, False, "Label 42")
    for tname, t in TRANSFORMS.items():
        if t:
            run_case(shape, 20, tname, t, True, "Label 42")
for text in ["gy", "A much longer label on one line", " ", "", "Ünïcödé ÅØ", "日本"]:
    run_case("cube", 20, "applied", None, True, text)



# Sequences: several decals, editing, removing. Each check is (description, passed).
def uv_values(obj, img, faces):
    uv = obj.data.uv_layers[img.decal_press.uv_map]
    return [tuple(uv.data[i].uv) for p in obj.data.polygons if p.index in faces
            for i in p.loop_indices]


def remove(obj, img):
    bpy.context.view_layer.objects.active = obj
    return bpy.ops.decal_press.remove(image=img.name)


def tidy(obj):
    """Back to one plain material and one UV map, nothing left over."""
    return (len(obj.material_slots) <= 1 and len(obj.data.uv_layers) == 1
            and not [i for i in bpy.data.images if i.decal_press.is_decal]
            and not [m for m in bpy.data.materials if dp.MADE_KEY in m])


def sequences():
    checks = []
    front = lambda f: f.normal.y < -0.9  # noqa: E731

    clear()
    obj, _ = build("dense_cube", 20)
    obj.data.materials.append(body_material())
    _, a, sa = add_decal(obj, lambda f: front(f) and f.calc_center_median().x > 0, "Right")
    before = uv_values(obj, a, sa)
    _, b, sb = add_decal(obj, front, "Whole")
    checks.append(("overlapping decal leaves the first one's UVs alone",
                   uv_values(obj, a, sa) == before))
    checks.append(("overlapping decals use different UV maps",
                   a.decal_press.uv_map != b.decal_press.uv_map))
    remove(obj, a)
    checks.append(("second decal intact after removing the first",
                   not check("", obj, b, sb, {"FINISHED"})[0]))
    remove(obj, b)
    checks.append(("removing both leaves the part as it was", tidy(obj)))

    for shape in ("cube", "sphere"):
        clear()
        obj, _ = build(shape, 20)
        _, a, sa = add_decal(obj, lambda f: f.normal.y < -0.8, "Nomat")
        remove(obj, a)
        checks.append((f"{shape} without material: add then remove leaves no leftovers",
                       tidy(obj)))

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    for p in obj.data.polygons:
        p.material_index = 3
    r, a, sa = add_decal(obj, front, "Past")
    checks.append(("faces with a material index past the last slot don't all get the decal",
                   not check("", obj, a, sa, r)[0]
                   and sum(p.material_index == 1 for p in obj.data.polygons) == 1))

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    r, a, _ = add_decal(obj, lambda f: True, "All")
    checks.append(("selecting a whole closed part is refused without leftovers",
                   r == {"CANCELLED"} and tidy(obj)
                   and all(p.material_index == 0 for p in obj.data.polygons)))

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    _, a, sa = add_decal(obj, front, "Edit")
    bpy.ops.object.mode_set(mode="EDIT")
    remove(obj, a)
    bpy.ops.object.mode_set(mode="OBJECT")
    checks.append(("remove in Edit Mode leaves no leftovers", tidy(obj)))

    shorts, letters = [], []
    for size in (2, 200):
        clear()
        obj, _ = build("cube", size)
        obj.data.materials.append(body_material())
        _, a, _ = add_decal(obj, front, "Same")
        shorts.append(min(a.size))
        letters.append(a.decal_press.letter_mm / size)
    checks.append(("text on a 2 mm and a 200 mm cube both get at least 256 px",
                   min(shorts) >= dp.MIN_TEXT_PIXELS))
    checks.append(("text on a 2 mm and a 200 mm cube has the same proportions",
                   letters[0] > 0 and abs(letters[0] / letters[1] - 1) < 0.02))

    for size in (20, 200):
        clear()
        obj, _ = build("cube", size)
        obj.data.materials.append(body_material())
        _, a, _ = add_decal(obj, front, "Height 42")
        a.decal_press.size_mode = "HEIGHT"
        a.decal_press.letter_height = 3.0
        checks.append((f"letter height 3 mm on a {size} mm cube gives 3 mm capitals",
                       abs(a.decal_press.letter_mm - 3.0) < 0.1))
    a.decal_press.margin = 0.3
    checks.append(("letter height holds when the margin changes",
                   abs(a.decal_press.letter_mm - 3.0) < 0.1))

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    _, a, sa = add_decal(obj, front, "Pick")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.decal_press.select(image=a.name)
    picked = {f.index for f in bmesh.from_edit_mesh(obj.data).faces if f.select}
    bpy.ops.object.mode_set(mode="OBJECT")
    checks.append(("Select Faces selects exactly the decal's faces", picked == sa))
    checks.append(("panel registered under the material slots",
                   dp.DECALPRESS_PT_material.is_registered
                   and not dp.DECALPRESS_PT_sidebar.is_registered))

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    _, a, _ = add_decal(obj, front, "Saved")
    a.decal_press.scale = 0.6
    a.decal_press.text_color = (0.8, 0.1, 0.1)
    px = np.empty(len(a.pixels), np.float32)
    a.pixels.foreach_get(px)
    size, name = tuple(a.size), a.name
    path = os.path.join(bpy.app.tempdir, "decal_press_saved.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    b = bpy.data.images.get(name)
    px2 = np.empty(len(b.pixels), np.float32) if b else None
    if b:
        b.pixels.foreach_get(px2)
    checks.append(("a decal resized and recolored survives saving and reopening",
                   b is not None and tuple(b.size) == size and b.packed_file is not None
                   and np.abs(px - px2).max() < 1 / 255 + 1e-6))
    os.remove(path)

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    logo = bpy.data.images.new("Logo", 300, 100, alpha=True)
    paint = np.zeros((100, 300, 4), np.float32)
    paint[20:80, 30:270] = (0.1, 0.2, 0.8, 1.0)
    logo.pixels.foreach_set(paint.ravel())  # painted in Blender: lost on reload unless packed
    bpy.context.scene.decal_press_new.kind, bpy.context.scene.decal_press_new.image = "IMAGE", logo
    r, a, sa = add_decal(obj, front, "", kind="IMAGE")
    bpy.context.scene.decal_press_new.kind = "TEXT"
    s = a.decal_press
    inner = (s.width_mm - 2 * s.pad_mm) / (s.height_mm - 2 * s.pad_mm)
    checks.append(("an image decal hugs the image (no padding to the face's shape)",
                   r == {"FINISHED"} and abs(inner / 3.0 - 1) < 0.02))
    path = os.path.join(bpy.app.tempdir, "decal_press_logo.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    checks.append(("a painted source image is packed on save, so the decal can be redrawn",
                   logo.packed_file is not None))
    os.remove(path)

    clear()
    obj, _ = build("cube", 20)
    obj.data.materials.append(body_material())
    _, a, _ = add_decal(obj, front, "Away")
    a.decal_press.offset = (100, 0)
    away = a.decal_press.off_faces
    a.decal_press.offset = (5, 0)
    checks.append(("a decal moved off its faces is flagged, and not when it's back",
                   away and not a.decal_press.off_faces))

    clear()
    one, _ = build("cube", 20)
    two, _ = build("cube", 20)
    two.location.x = 40
    for ob in (one, two):
        ob.data.materials.append(body_material())
        ob.select_set(True)
    bpy.context.view_layer.objects.active = one
    bpy.ops.object.mode_set(mode="EDIT")
    for ob in (one, two):
        bm = bmesh.from_edit_mesh(ob.data)
        for f in bm.faces:
            f.select = front(f)
        bmesh.update_edit_mesh(ob.data)
    bpy.context.scene.decal_press_new.text = "Both"
    r = bpy.ops.decal_press.add()
    bpy.ops.object.mode_set(mode="OBJECT")
    checks.append(("two objects in Edit Mode each get their own decal",
                   r == {"FINISHED"} and len(dp.object_decals(one)) == 1
                   and len(dp.object_decals(two)) == 1
                   and dp.object_decals(one) != dp.object_decals(two)))

    clear()
    obj, _ = build("cube", 2)
    obj.data.materials.append(body_material())
    add_decal(obj, front, "Tiny label")
    info = dp.decals_on(obj)
    checks.append(("decals_on lists the decal with its text and a small-letters problem",
                   len(info) == 1 and info[0]["text"] == "Tiny label"
                   and info[0]["problems"] == [f"letters under {dp.LEGIBLE_MM:g} mm"]))

    from types import SimpleNamespace
    real = dp._prefs
    dp._prefs = lambda: SimpleNamespace(panel_location="SIDEBAR", sidebar_tab="Print",
                                        default_font="")
    dp._register_panels()
    checks.append(("Sidebar preference moves the panel to the named tab",
                   dp.DECALPRESS_PT_sidebar.is_registered
                   and not dp.DECALPRESS_PT_material.is_registered
                   and dp.DECALPRESS_PT_sidebar.bl_category == "Print"))
    dp._prefs = real
    dp._register_panels()

    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} sequence: {name}")
        if not ok:
            FAILS.append((name, ["sequence"]))


sequences()
print(f"\n{len(FAILS)} failing cases")
sys.exit(1 if FAILS else 0)
