# SPDX-License-Identifier: MIT
"""Classic Mod/ loader entry point (GUI side) for the Visibility Sets addon.

Runs <addon>/InitGui.py (exact capitalisation, same Linux case-sensitivity
caveat as Init.py) at GUI startup and defers to
freecad/VisibilitySets/init_gui.py, which is idempotent against being
loaded twice (here and by the modern namespace-package loader).
"""
import FreeCAD as App

try:
    from freecad.VisibilitySets import init_gui as _init_gui  # noqa: F401
except Exception as exc:  # never break GUI startup
    App.Console.PrintError("Visibility Sets: GUI load failed: %s\n" % exc)
