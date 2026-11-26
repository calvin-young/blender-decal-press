# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Calvin Young
"""Decals survive 3MF export through blender-3mf-io (needs its layered-texture export).

MF=<folder containing io_mesh_3mf> [OUT=<folder to keep the .3mf files>] blender -b --factory-startup --python tests/blender/check_export.py

For example, a copy of the fork's test-all-prs branch:
    git -C ~/dev/blender-3mf-io archive test-all-prs io_mesh_3mf | tar -x -C /tmp/mf
    MF=/tmp/mf blender -b --factory-startup --python tests/blender/check_export.py

Checks the 3MF's XML: a layered decal is a <multiproperties> group (base color + texture)
on exactly the decal's triangles, clipped outside the image (tilestyle none), with its PNG
in the package; a Replace decal is a plain texture. Exits with status 1 on any failure.
"""
import os
import re
import sys
import tempfile
import zipfile

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ["MF"])
sys.argv = [sys.argv[0]]
exec(open(os.path.join(HERE, "check_decals.py")).read().split("SHAPES = [")[0])  # helpers
import io_mesh_3mf  # noqa: E402

io_mesh_3mf.register()
from io_mesh_3mf import api  # noqa: E402

OUT = os.environ.get("OUT") or tempfile.mkdtemp(prefix="decal_press_export_")  # OUT keeps the files
os.makedirs(OUT, exist_ok=True)
front = lambda f: f.normal.y < -0.9  # noqa: E731
results = []


def export(name):
    path = os.path.join(OUT, name + ".3mf")
    api.export_3mf(path, objects=[o for o in bpy.data.objects if o.type == "MESH"])
    z = zipfile.ZipFile(path)
    model = z.read("3D/3dmodel.model").decode()
    textures = [n for n in z.namelist() if n.lower().endswith(".png") and "Textures" in n]
    pids = {}
    for t in re.findall(r"<(?:\w+:)?triangle [^>]*>", model):
        m = re.search(r'pid="(\d+)"', t)
        if m:
            pids[m.group(1)] = pids.get(m.group(1), 0) + 1
    multi = re.findall(r'<(?:\w+:)?multiproperties id="(\d+)"', model)
    return model, textures, pids, multi


def check_(name, ok):
    results.append((name, ok))
    print(f"{'ok  ' if ok else 'FAIL'} {name}")


clear()
obj, _ = build("cube", 20)
obj.data.materials.append(body_material())
add_decal(obj, front, "Layer 42")
model, textures, pids, multi = export("layer")
check_("layered decal exports as one multiproperties group with its texture",
       len(multi) == 1 and textures == ["3D/Textures/Decal_Layer_42.png"])
check_("the group covers exactly the decal's 2 triangles", pids.get(multi[0] if multi else "") == 2)
check_("the texture is clipped outside the image (tilestyle none)", 'tilestyleu="none"' in model)

clear()
obj, _ = build("cube", 20)
add_decal(obj, front, "No material")
model, textures, pids, multi = export("no_material")
check_("on an object without a material, only the decal's triangles carry it",
       len(multi) == 1 and pids == {multi[0]: 2})

clear()
obj, _ = build("dense_cube", 20)
obj.data.materials.append(body_material())
add_decal(obj, lambda f: front(f) and f.calc_center_median().x > 0, "Right")
add_decal(obj, front, "Whole")
model, textures, pids, multi = export("overlap")
check_("overlapping decals export as two groups, 64 triangles each, with both textures",
       len(multi) == 2 and all(pids.get(m) == 64 for m in multi) and len(textures) == 2)

clear()
obj, _ = build("cube", 20)
obj.data.materials.append(body_material())
bpy.context.scene.decal_press_new.mode = "REPLACE"
add_decal(obj, front, "Replace")
bpy.context.scene.decal_press_new.mode = "LAYER"
model, textures, pids, multi = export("replace")
check_("a Replace decal exports as a plain texture", not multi and len(textures) == 1)

failed = [n for n, ok in results if not ok]
print(f"\n{len(failed)} failing checks")
sys.stdout.flush()
os._exit(1 if failed else 0)
