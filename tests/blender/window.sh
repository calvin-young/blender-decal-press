#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run a test script in a real Blender window, with a throwaway user config that has no splash.
# Usage: tests/blender/window.sh SCRIPT.py [script args...]
#   tests/blender/window.sh screenshots.py --out ~/decal_press_tests/window
#   tests/blender/window.sh check_undo.py
set -e
here=$(cd "$(dirname "$0")" && pwd)
script=$1; shift
cfg=$(mktemp -d)
trap 'rm -rf "$cfg"' EXIT
export BLENDER_USER_CONFIG=$cfg
blender --background --factory-startup --python-expr \
  "import bpy; bpy.context.preferences.view.show_splash = False; bpy.ops.wm.save_userpref()" > /dev/null
DISPLAY=${DISPLAY:-:0} blender -p 0 0 1920 1080 --python "$here/$script" -- "$@"
