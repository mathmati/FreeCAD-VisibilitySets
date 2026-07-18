# DRAFT/UNVERIFIED -- written 2026-07-18; never executed. The build machine
# had FreeCAD's console (freecadcmd) but no GUI session was launched, so this
# driver has not run once. Run it with the GUI executable and adjust before
# trusting or committing it.
# SPDX-License-Identifier: MIT
"""verify/drivers/visibility_driver.py -- GUI verification driver.

Run from the repo root with the GUI executable:

    freecad verify/drivers/visibility_driver.py

(or under Linux: xvfb-run -a -s "-screen 0 1280x1024x24" freecad ...)

Builds a small sample assembly (an App::Part with two solids plus one loose
solid), then drives the REAL command classes the toolbar buttons invoke,
with the real Gui.Selection API for picks:

  1. Isolate: select Bracket, IsolateCommand().Activated() -> assert every
     other object's ViewObject.Visibility is False, except the Assembly
     container holding Bracket, which must stay visible (hiding an
     App::Part hides its whole subtree); screenshot.
  2. Restore: RestoreCommand().Activated() -> assert the stack entry brought
     the pre-isolate state back (all visible); screenshot.
  3. Transparent others: select Pin, TransparentOthersCommand().Activated()
     -> assert the complement sits at 80% transparency; screenshot.
  4. Save/Apply set: the Save set command's QInputDialog cannot be driven
     from a script, so the set is written through the same store call the
     command makes (store.save_set), then ApplySetCommand("...").Activated()
     -> assert the map applied and vanished/new objects behave as documented.

Result is printed to stdout AND written to
verify/out/visibility_driver.result.txt (grep that file; GUI startup
scripts do not reliably propagate process exit codes). Screenshots land in
verify/out/ and can be copied to docs/screenshots/ once this has run.
"""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_OUT_DIR = os.path.join(_REPO_ROOT, "verify", "out")
try:
    import freecad
    freecad.__path__ = [os.path.join(_REPO_ROOT, "freecad")] + list(freecad.__path__)
except ImportError:
    sys.path.insert(0, _REPO_ROOT)

import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402

from freecad.VisibilitySets import store, viewadapter  # noqa: E402
from freecad.VisibilitySets.commands import (  # noqa: E402
    ApplySetCommand,
    IsolateCommand,
    RestoreCommand,
    TransparentOthersCommand,
)

RESULT_PATH = os.path.join(_OUT_DIR, "visibility_driver.result.txt")
_fails = []


def record(name, fn):
    try:
        fn()
    except Exception:
        _fails.append(name)
        print("[FAIL] %s" % name)
        traceback.print_exc()
    else:
        print("[ ok ] %s" % name)


def pump(n=5):
    from PySide import QtWidgets
    app = QtWidgets.QApplication.instance()
    for _ in range(n):
        app.processEvents()
    try:
        Gui.updateGui()
    except Exception:
        pass


def shot(filename):
    os.makedirs(_OUT_DIR, exist_ok=True)
    Gui.ActiveDocument.ActiveView.saveImage(
        os.path.join(_OUT_DIR, filename), 1280, 1024, "Current")


def visibility(doc, name):
    return bool(doc.getObject(name).ViewObject.Visibility)


def transparency(doc, name):
    """None for objects whose view provider has no Transparency (e.g.
    App::Part containers) -- the addon skips those by design."""
    return getattr(doc.getObject(name).ViewObject, "Transparency", None)


def main():
    doc = App.newDocument("VisSetsGuiDriver")
    assembly = doc.addObject("App::Part", "Assembly")
    bracket = doc.addObject("Part::Box", "Bracket")
    pin = doc.addObject("Part::Cylinder", "Pin")
    assembly.addObject(bracket)
    assembly.addObject(pin)
    doc.addObject("Part::Sphere", "Ball")
    doc.recompute()
    pump()

    def s1_isolate():
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(bracket)
        IsolateCommand().Activated()
        pump()
        assert visibility(doc, "Bracket"), "Bracket not visible after isolate"
        assert visibility(doc, "Assembly"), \
            "Assembly (the selection's container) must stay visible"
        for name in ("Pin", "Ball"):
            assert not visibility(doc, name), "%s still visible" % name
        shot("vis_isolate.png")

    def s2_restore():
        RestoreCommand().Activated()
        pump()
        for name in ("Assembly", "Bracket", "Pin", "Ball"):
            assert visibility(doc, name), "%s not restored" % name
        shot("vis_restored.png")

    def s3_transparent_others():
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(pin)
        TransparentOthersCommand().Activated()
        pump()
        assert transparency(doc, "Pin") == 0, "Pin was faded"
        for name in ("Bracket", "Ball"):
            assert transparency(doc, name) == 80, \
                "%s transparency is %r" % (name, transparency(doc, name))
        # App::Part containers have no Transparency in 1.1.1; they are
        # skipped by the fade by design.
        assert transparency(doc, "Assembly") is None, \
            "Assembly unexpectedly gained a Transparency attribute"
        shot("vis_transparent_others.png")
        RestoreCommand().Activated()
        pump()

    def s4_save_and_apply_set():
        mgr = store.get_or_create_manager(doc)
        store.save_set(mgr, "bracket only",
                       {"Assembly": True, "Bracket": True,
                        "Pin": False, "Ball": False})
        ApplySetCommand("bracket only").Activated()
        pump()
        assert visibility(doc, "Bracket") and not visibility(doc, "Ball"), \
            "saved set did not apply"
        shot("vis_applied_set.png")
        RestoreCommand().Activated()
        pump()

    record("isolate selection hides everything else", s1_isolate)
    record("restore pops the stack back to the pre-isolate state", s2_restore)
    record("transparent others fades the complement to 80%", s3_transparent_others)
    record("saved set applies via the submenu command", s4_save_and_apply_set)

    os.makedirs(_OUT_DIR, exist_ok=True)
    verdict = "PASS" if not _fails else "FAIL (%d)" % len(_fails)
    with open(RESULT_PATH, "w") as f:
        f.write(verdict + "\n")
    print("visibility driver: %s" % verdict)


main()
