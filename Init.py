# SPDX-License-Identifier: MIT
"""Classic Mod/ loader entry point (App side) for the Visibility Sets addon.

The classic loader runs <addon>/Init.py at application start; the file name
must use exactly this capitalisation (a lowercase init.py is silently
ignored on case-sensitive filesystems, i.e. Linux). The modern
namespace-package loader does not need this file; it exists so both loaders
work.

The one useful App-side job: importing the store module makes the
FeaturePython proxy class importable early, so saved documents holding a
Visibility Sets manager restore their proxy without timing surprises.
"""
import FreeCAD as App

try:
    from freecad.VisibilitySets import store as _store  # noqa: F401
except Exception as exc:  # never break application startup
    App.Console.PrintError("Visibility Sets: App-side import failed: %s\n" % exc)
