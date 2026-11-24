# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young
"""Undo and redo bring back a decal's pixels, not only its settings.

tests/blender/window.sh check_undo.py   (needs a real window: undo doesn't run in --background)

Exits with status 1 if the image after undo or redo differs from the one drawn for that text.
"""
import hashlib
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import decal_press as dp  # noqa: E402

dp.register()
state = {}
def digest(img):
    px = np.empty(len(img.pixels), np.float32); img.pixels.foreach_get(px)
    return hashlib.md5(px.tobytes()).hexdigest()[:8], tuple(img.size)
def win_override():
    win = bpy.context.window_manager.windows[0]
    a = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    return bpy.context.temp_override(window=win, area=a, region=next(r for r in a.regions if r.type == "WINDOW"))
def step1():
    o = bpy.data.objects["Cube"]
    bpy.context.view_layer.objects.active = o
    with win_override():
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(o.data)
        for f in bm.faces: f.select = f.normal.y < -0.9
        bmesh.update_edit_mesh(o.data)
        bpy.context.scene.decal_press_new.text = "First"
        print("add", bpy.ops.decal_press.add())
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.ed.undo_push(message="after add")
    img = [i for i in bpy.data.images if i.decal_press.is_decal][0]
    state["first"] = digest(img); state["name"] = img.name
def step2():
    img = bpy.data.images[state["name"]]
    img.decal_press.text = "Second longer"
    with win_override():
        bpy.ops.ed.undo_push(message="text")
    state["second"] = digest([i for i in bpy.data.images if i.decal_press.is_decal][0])
def step3():
    with win_override():
        bpy.ops.ed.undo()
def step4():
    img = [i for i in bpy.data.images if i.decal_press.is_decal][0]
    print("UNDO text now", repr(img.decal_press.text), "name", img.name)
    state["undo"] = digest(img)
    print("UNDO first", state["first"], "second", state["second"], "after undo", state["undo"])
    with win_override():
        bpy.ops.ed.redo()
def step5():
    img = [i for i in bpy.data.images if i.decal_press.is_decal][0]
    print("REDO text now", repr(img.decal_press.text), digest(img))
    state["redo"] = digest(img)
    ok = state["undo"] == state["first"] and state["redo"] == state["second"]
    print("ok   undo and redo restore the pixels" if ok else "FAIL undo or redo left stale pixels")
    state["status"] = 0 if ok else 1
    bpy.ops.wm.quit_blender()
steps = [step1, step2, step3, step4, step5]
def tick():
    try:
        steps.pop(0)()
    except Exception:
        import traceback; traceback.print_exc(); bpy.ops.wm.quit_blender()
    return 1.0 if steps else None
bpy.app.timers.register(tick, first_interval=2)


def _exit_status():
    sys.stdout.flush()
    os._exit(state.get("status", 1))


import atexit  # noqa: E402

atexit.register(_exit_status)
