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
    new = scene.decal_press_new
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
            if -0.02 <= u <= 1.02 and -0.02 <= v <= 1.02:
                inside += 1
            else:
                outside += 1
    if mirrored:
        problems.append(f"mirrored on {mirrored} faces")
    if upside_down:
        problems.append(f"upside down on {upside_down} faces")

    # Fit: the decal is no bigger than the faces it sits on.
    w_px, h_px = img.size
    if s.height_mm <= 0 or s.width_mm <= 0:
        problems.append("zero size")
    else:
        aspect_mm = s.width_mm / s.height_mm
        aspect_px = w_px / h_px
        if abs(aspect_px / aspect_mm - 1) > 0.03:
            problems.append(f"stretched: {aspect_mm:.3f} mm aspect vs {aspect_px:.3f} px")
    world_pts = [mw @ me.vertices[v].co for p in me.polygons if p.index in selected
                 for v in p.vertices]
    span = max((a - b).length for a in world_pts[:200] for b in world_pts[:200])
    if max(s.width_mm, s.height_mm) > span * 1.05:
        problems.append(f"decal {s.width_mm:.2f} mm wider than the faces ({span:.2f} mm)")

    # Legibility: letter height in pixels. The text fills (1 - 2 margin) of the short side.
    letter_px = min(w_px, h_px) * (1 - 2 * s.margin)
    if letter_px < 48:
        problems.append(f"letters only {letter_px:.0f} px tall")
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

    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} sequence: {name}")
        if not ok:
            FAILS.append((name, ["sequence"]))


sequences()
print(f"\n{len(FAILS)} failing cases")
sys.exit(1 if FAILS else 0)
