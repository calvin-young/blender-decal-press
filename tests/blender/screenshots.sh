#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Run screenshots.py in a real window with a throwaway user config that has no splash.
# Usage: tests/blender/screenshots.sh [OUT_DIR] [--keep]
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$HOME/decal_press_tests/window}
cfg=$(mktemp -d)
trap 'rm -rf "$cfg"' EXIT
export BLENDER_USER_CONFIG=$cfg
blender --background --factory-startup --python-expr \
  "import bpy; bpy.context.preferences.view.show_splash = False; bpy.ops.wm.save_userpref()" > /dev/null
DISPLAY=${DISPLAY:-:0} blender -p 0 0 1920 1080 \
  --python "$here/screenshots.py" -- --out "$out" "${@:2}"
