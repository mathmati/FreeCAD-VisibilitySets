# SPDX-License-Identifier: MIT
"""Visibility Sets workbench package (modern namespaced layout).

Importing this package has no side effects beyond making the submodules
importable: workbench and command registration happens in init_gui.py,
loaded by FreeCAD's addon machinery (or the root InitGui.py shim) when the
GUI starts. core.py and store.py import cleanly without a GUI.
"""
