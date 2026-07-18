# SPDX-License-Identifier: MIT
"""Workbench registration for the Visibility Sets addon.

Importing this module registers the workbench with Gui.addWorkbench(...).
It is picked up by FreeCAD's modern addon loader (freecad/<pkg>/init_gui.py)
and by the root InitGui.py shim for the classic Mod/ loader; the guard at
the bottom keeps a loader that fires both paths from registering twice.
Nothing runs at import time beyond the registration itself.
"""
import os

import FreeCADGui as Gui


class VisibilitySetsWorkbench(Gui.Workbench):
    MenuText = "Visibility Sets"
    ToolTip = ("Isolate parts, fade everything else, and keep named "
               "visibility sets inside the document")
    Icon = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "Resources",
        "Icons",
        "visibilitysets.svg",
    )

    def Initialize(self):
        # Import side effect registers the base commands with Gui.addCommand.
        from . import commands

        commands.register()
        cmds = [
            "VisibilitySets_Isolate",
            "VisibilitySets_TransparentOthers",
            "VisibilitySets_Restore",
            "Separator",
            "VisibilitySets_SaveSet",
        ]
        self.appendToolbar("Visibility Sets", [c for c in cmds if c != "Separator"])
        self.appendMenu("Visibility Sets", cmds)
        commands.refresh_apply_menu(self)

    def Activated(self):
        from . import commands

        commands.refresh_apply_menu(self)

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"  # exact string, mandatory, do not change


if "VisibilitySetsWorkbench" not in Gui.listWorkbenches():
    Gui.addWorkbench(VisibilitySetsWorkbench())
