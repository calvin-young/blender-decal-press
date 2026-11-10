# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young
"""Render text decals on awkward synthetic shapes, one PNG each.

blender -b --factory-startup --python tests/blender/shapes.py
Writes to $OUT (default ~/decal_press_tests) and prints each decal's size.
Look at the images: nothing here judges them.
"""
import bpy, bmesh, sys, os, math, mathutils
from mathutils import Vector
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.environ.get("OUT", os.path.expanduser("~/decal_press_tests")); TAG = os.environ.get("TAG", "shape")
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
import decal_press as dp; dp.register()
sc = bpy.context.scene
body = bpy.data.materials.new("Body")
if not body.node_tree: body.use_nodes = True
body.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.35, 0.45, 1)

def finish(o):
    o.data.materials.clear(); o.data.materials.append(body)

def build(name):
    if name == "suzanne_face":
        bpy.ops.mesh.primitive_monkey_add(size=40)
        o = bpy.context.active_object
        m = o.modifiers.new("s", "SUBSURF"); m.levels = 1
        bpy.ops.object.modifier_apply(modifier="s")
        sel = lambda f, c: f.normal.y < -0.7 and c.z > 4 and abs(c.x) < 14
    elif name == "suzanne_cheek":
        bpy.ops.mesh.primitive_monkey_add(size=40)
        o = bpy.context.active_object
        sel = lambda f, c: f.normal.y < -0.5
    elif name == "cylinder_band":
        bpy.ops.mesh.primitive_cylinder_add(radius=15, depth=30, vertices=32)
        o = bpy.context.active_object
        sel = lambda f, c: abs(f.normal.z) < 0.1 and f.normal.y < -0.5
    elif name == "cylinder_cap":
        bpy.ops.mesh.primitive_cylinder_add(radius=15, depth=10, vertices=32)
        o = bpy.context.active_object
        sel = lambda f, c: f.normal.z > 0.9
    elif name == "triangle":
        bpy.ops.mesh.primitive_cylinder_add(radius=20, depth=5, vertices=3, rotation=(0, 0, 0.4))
        o = bpy.context.active_object
        sel = lambda f, c: f.normal.z > 0.9
    elif name == "L_plate":
        me = bpy.data.meshes.new("L"); bm = bmesh.new()
        pts = [(0, 0), (60, 0), (60, 15), (15, 15), (15, 40), (0, 40)]
        bot = [bm.verts.new((x, y, 0)) for x, y in pts]
        top = [bm.verts.new((x, y, 4)) for x, y in pts]
        bm.faces.new(top); bm.faces.new(list(reversed(bot)))
        for i in range(6):
            j = (i + 1) % 6; bm.faces.new((bot[i], bot[j], top[j], top[i]))
        bm.normal_update(); bm.to_mesh(me)
        o = bpy.data.objects.new("L", me); sc.collection.objects.link(o)
        bpy.context.view_layer.objects.active = o; o.select_set(True)
        o.rotation_euler.z = math.radians(30); bpy.ops.object.transform_apply(rotation=True)
        sel = lambda f, c: f.normal.z > 0.9
    elif name == "slanted_wall":
        bpy.ops.mesh.primitive_cube_add(size=1)
        o = bpy.context.active_object; o.scale = (50, 4, 20)
        o.rotation_euler = (math.radians(20), 0, math.radians(37))
        bpy.ops.object.transform_apply(rotation=True, scale=True)
        n0 = mathutils.Euler((math.radians(20), 0, math.radians(37))).to_matrix() @ Vector((0, -1, 0))
        sel = lambda f, c: f.normal.dot(n0) > 0.9
    elif name == "sphere_patch":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=20)
        o = bpy.context.active_object
        sel = lambda f, c: f.normal.y < -0.75
    finish(o)
    return o, sel

def run(name, text, after=None, tag=""):
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob)
    for im in [i for i in bpy.data.images if i.decal_press.is_decal]: bpy.data.images.remove(im)
    for m in [m for m in bpy.data.materials if m != body]: bpy.data.materials.remove(m)
    o, sel = build(name)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(o.data)
    n = 0
    for f in bm.faces:
        f.select = sel(f, f.calc_center_median()); n += f.select
    bmesh.update_edit_mesh(o.data)
    new = sc.decal_press_new; new.kind = "TEXT"; new.text = text
    r = bpy.ops.decal_press.add()
    img = [i for i in bpy.data.images if i.decal_press.is_decal][-1]
    if after: after(img)
    bm = bmesh.from_edit_mesh(o.data)
    fs = [f for f in bm.faces if f.select]
    c = sum((f.calc_center_median() * f.calc_area() for f in fs), Vector()) / sum(f.calc_area() for f in fs)
    nrm = sum((f.normal * f.calc_area() for f in fs), Vector()).normalized()
    bpy.ops.object.mode_set(mode="OBJECT")
    s = img.decal_press
    print(name, r, n, "faces", f"{s.width_mm:.1f}x{s.height_mm:.1f}mm", img.size[:])
    cam = bpy.data.cameras.new("c"); cam.type = "ORTHO"; cam.ortho_scale = 70
    co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
    co.location = c + nrm * 150
    up = Vector((0, 0, 1)) if abs(nrm.z) < 0.9 else Vector((0, 1, 0))
    if abs(nrm.z) > 0.9:
        co.rotation_euler = (0, 0, 0) if nrm.z > 0 else (math.pi, 0, 0)
    else:
        z = nrm; x = Vector((0, 0, 1)).cross(z).normalized(); y = z.cross(x)
        co.rotation_euler = mathutils.Matrix((x, y, z)).transposed().to_euler()
    sc.render.engine = "BLENDER_EEVEE"; sc.render.resolution_x = sc.render.resolution_y = 500
    if not sc.world:
        w = bpy.data.worlds.new("w"); sc.world = w
        if not w.node_tree: w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    sc.view_settings.view_transform = "Standard"
    sc.render.filepath = f"{OUT}/{TAG}_{name}{tag}.png"
    bpy.ops.render.render(write_still=True)

for name, text in [("suzanne_face", "SUZANNE"), ("suzanne_cheek", "Cheek"),
                   ("cylinder_band", "Cylinder_band"), ("cylinder_cap", "Cap_32"),
                   ("triangle", "Triangle"), ("L_plate", "L_shape_part"),
                   ("slanted_wall", "Slanted_wall_37deg"), ("sphere_patch", "Sphere")]:
    run(name, text)
def tweak(img):
    s = img.decal_press; s.offset = (5, -3); s.angle = math.radians(15); s.scale = 0.7
run("slanted_wall", "Moved_turned_scaled", tweak, "_tweak")
def other(img): bpy.ops.decal_press.rotate(image=img.name)
run("L_plate", "Other_side", other, "_rot90")
def bounds(img): img.decal_press.fit = "BOUNDS"
run("triangle", "Bounds", bounds, "_bounds")
def edit(img): img.decal_press.text = "A much longer label now"
run("L_plate", "short", edit, "_edit")
