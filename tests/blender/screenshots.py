# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young
"""Screenshots of decals in a real Blender window, for looking at, not judging.

tests/blender/screenshots.sh [OUT_DIR] [--keep]

A fresh user config opens on Blender's Quick Setup splash. Point BLENDER_USER_CONFIG at a folder
whose userpref.blend has the splash turned off (tests/blender/screenshots.sh does this).

Sets up synthetic parts (the default 2 mm cube, a 100 mm block with its scale
not applied, a cylinder and Suzanne without materials), adds text decals with
the real operator, and saves window screenshots: front and back in Material
Preview, front in Solid shading, and the Material tab's panel.
"""
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import decal_press as dp  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[argv.index("--out") + 1] if "--out" in argv else os.path.expanduser("~/decal_press_tests/window")
KEEP = "--keep" in argv
os.makedirs(OUT, exist_ok=True)
dp.register()


def area(kind):
    win = bpy.context.window_manager.windows[0]
    a = next(a for a in win.screen.areas if a.type == kind)
    return win, a, next(r for r in a.regions if r.type == "WINDOW")


def view(axis, shading="MATERIAL"):
    win, a, r = area("VIEW_3D")
    a.spaces[0].shading.type = shading
    a.spaces[0].overlay.show_floor = False
    with bpy.context.temp_override(window=win, area=a, region=r):
        bpy.ops.view3d.view_axis(type=axis)
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.view3d.view_selected()
        bpy.ops.object.select_all(action="DESELECT")


def add_text(obj, pick, text):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    for f in bm.faces:
        f.select = pick(f)
    bmesh.update_edit_mesh(obj.data)
    new = bpy.context.scene.decal_press_new
    new.kind, new.text = "TEXT", text
    print("add", text, bpy.ops.decal_press.add())
    bpy.ops.object.mode_set(mode="OBJECT")


def setup():
    scene = bpy.context.scene
    for name in ("Camera", "Light"):
        bpy.data.objects.remove(bpy.data.objects[name])
    cube = bpy.data.objects["Cube"]  # 2 mm, with its default material
    add_text(cube, lambda f: f.normal.y < -0.9, "Cube 2mm")

    bpy.ops.mesh.primitive_cube_add(size=1, location=(6, 0, 0))
    block = bpy.context.object
    block.scale = (4, 1.5, 2)  # 4 x 1.5 x 2 mm, scale not applied
    add_text(block, lambda f: f.normal.y < -0.9, "Unapplied")

    bpy.ops.mesh.primitive_cylinder_add(radius=1.5, depth=3, location=(-6, 0, 0), vertices=48)
    add_text(bpy.context.object, lambda f: f.normal.z > 0.9, "Cap")

    bpy.ops.mesh.primitive_monkey_add(size=3, location=(0, 0, 4))
    add_text(bpy.context.object, lambda f: f.normal.y < -0.5, "Suzanne")
    bpy.context.view_layer.objects.active = cube
    scene.render.engine = "BLENDER_EEVEE"


def shot(name):
    path = os.path.join(OUT, name + ".png")
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=path)
    print("shot", path)


STEPS = [
    lambda: setup(),
    lambda: view("FRONT"),
    lambda: shot("front_material"),
    lambda: view("BACK"),
    lambda: shot("back_material"),
    lambda: view("FRONT", "SOLID"),
    lambda: shot("front_solid"),
    lambda: setattr(area("PROPERTIES")[1].spaces[0], "context", "MATERIAL"),
    lambda: shot("material_tab"),
]


def tick():
    if not STEPS:
        if not KEEP:
            bpy.ops.wm.quit_blender()
        return None
    try:
        STEPS.pop(0)()
    except Exception:
        import traceback
        traceback.print_exc()
        STEPS.clear()
    return 1.0


bpy.app.timers.register(tick, first_interval=2.0)
