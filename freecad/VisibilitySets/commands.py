# SPDX-License-Identifier: MIT
"""freecad.VisibilitySets.commands -- the toolbar/menu commands (GUI only).

Undo honesty: ``ViewObject.Visibility`` and ``ViewObject.Transparency``
are not covered by FreeCAD's undo system (they are view state and live
outside document transactions), so Isolate / Transparent others / Restore
do not open transactions that would record nothing; the addon's own
restore stack is the undo path for them. Saving a named set changes a
document property, which IS transactional, so Save set wraps its write in
openTransaction/commitTransaction and undo works there the normal way.
"""
import os

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from . import core, store, viewadapter

_ICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Resources",
    "Icons",
    "visibilitysets.svg",
)


def _status(msg):
    App.Console.PrintMessage(msg + "\n")
    try:
        Gui.getMainWindow().statusBar().showMessage(msg, 5000)
    except Exception:
        pass


def _selected_names(doc):
    """Selected object names in the active document (manager excluded),
    deduplicated, selection order kept."""
    names = []
    for sel in Gui.Selection.getSelection():
        # 1.1.1's getSelection() returns plain document objects; older
        # versions return SelectionObject wrappers with an .Object attribute.
        obj = getattr(sel, "Object", sel)
        if obj is None or getattr(obj, "Document", None) is not doc:
            continue
        if store.is_manager_object(obj):
            continue
        if obj.Name not in names:
            names.append(obj.Name)
    return names


class _BaseCommand(object):
    MENU_TEXT = ""
    TOOL_TIP = ""

    def GetResources(self):
        return {"MenuText": self.MENU_TEXT, "ToolTip": self.TOOL_TIP,
                "Pixmap": _ICON_PATH}

    def IsActive(self):
        return App.ActiveDocument is not None


class IsolateCommand(_BaseCommand):
    """Hide everything except the selected objects."""

    MENU_TEXT = "Isolate selection"
    TOOL_TIP = ("Hide everything except the selected objects. The previous "
                "view state is pushed onto the document's restore stack.")

    def Activated(self):
        doc = App.ActiveDocument
        selected = _selected_names(doc)
        if not selected:
            _status("Visibility Sets: select one or more objects to isolate first.")
            return
        try:
            vmap = core.isolate(selected, viewadapter.current_names(doc))
        except core.VisibilitySetError as exc:
            _status("Visibility Sets: %s" % exc)
            return
        mgr = store.get_or_create_manager(doc)
        store.push_snapshot(mgr, viewadapter.snapshot(doc), label="isolate")
        viewadapter.apply_visibility(vmap, doc)
        _status("Visibility Sets: isolated %d object(s); everything else hidden."
                % len(selected))


class TransparentOthersCommand(_BaseCommand):
    """Fade everything except the selected objects."""

    MENU_TEXT = "Transparent others"
    TOOL_TIP = ("Make everything except the selected objects %d%% transparent. "
                "The previous view state is pushed onto the restore stack."
                % viewadapter.DEFAULT_OTHER_TRANSPARENCY)

    def Activated(self):
        doc = App.ActiveDocument
        selected = _selected_names(doc)
        if not selected:
            _status("Visibility Sets: select one or more objects first.")
            return
        mgr = store.get_or_create_manager(doc)
        store.push_snapshot(mgr, viewadapter.snapshot(doc),
                            label="transparent others")
        faded = viewadapter.fade_others(selected, doc=doc)
        _status("Visibility Sets: faded %d object(s) to %d%% transparency."
                % (len(faded), viewadapter.DEFAULT_OTHER_TRANSPARENCY))


class RestoreCommand(_BaseCommand):
    """Pop the restore stack, or show everything if it is empty."""

    MENU_TEXT = "Restore visibility"
    TOOL_TIP = ("Restore the previous view state from the document's restore "
                "stack; if the stack is empty, show everything at 0% "
                "transparency.")

    def Activated(self):
        doc = App.ActiveDocument
        mgr = store.get_manager(doc)
        entry = store.pop_snapshot(mgr) if mgr is not None else None
        if entry is not None:
            viewadapter.apply_snapshot(entry, doc)
            _status("Visibility Sets: restored previous state (%s)."
                    % (entry.get("label") or "snapshot"))
        else:
            names = viewadapter.current_names(doc)
            viewadapter.apply_visibility(core.show_all(names), doc)
            viewadapter.apply_transparency({n: 0 for n in names}, doc)
            _status("Visibility Sets: restore stack empty; all objects shown.")


class SaveSetCommand(_BaseCommand):
    """Save the current view state as a named set stored in the document."""

    MENU_TEXT = "Save set..."
    TOOL_TIP = ("Save the current visibility state as a named set, stored "
                "inside the .FCStd file. Saving over an existing name "
                "overwrites it.")

    def Activated(self):
        doc = App.ActiveDocument
        mgr = store.get_or_create_manager(doc)
        name, ok = QtWidgets.QInputDialog.getText(
            Gui.getMainWindow(), "Save visibility set",
            "Name for the current visibility state:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        snap = viewadapter.snapshot(doc)
        doc.openTransaction("Save visibility set")
        try:
            store.save_set(mgr, name, snap["visibility"])
        except Exception:
            doc.abortTransaction()
            raise
        doc.commitTransaction()
        refresh_apply_menu()
        _status("Visibility Sets: saved set '%s' (%d objects)."
                % (name, len(snap["visibility"])))


class ApplySetCommand(_BaseCommand):
    """One per saved set; lives in the 'Apply set' submenu."""

    def __init__(self, set_name):
        self.set_name = set_name

    def GetResources(self):
        return {"MenuText": self.set_name,
                "ToolTip": ("Apply the saved set '%s'. Objects added since it "
                            "was saved keep their current state; objects that "
                            "vanished are reported." % self.set_name),
                "Pixmap": _ICON_PATH}

    def Activated(self):
        doc = App.ActiveDocument
        mgr = store.get_manager(doc)
        if mgr is None:
            _status("Visibility Sets: this document has no saved sets.")
            return
        try:
            vmap, dropped = store.resolve_set(
                mgr, self.set_name, viewadapter.current_names(doc))
        except core.VisibilitySetError as exc:
            _status("Visibility Sets: %s" % exc)
            return
        store.push_snapshot(mgr, viewadapter.snapshot(doc),
                            label="apply set: %s" % self.set_name)
        viewadapter.apply_visibility(vmap, doc)
        msg = "Visibility Sets: applied set '%s'." % self.set_name
        if dropped:
            msg += " Dropped %d vanished object(s): %s." % (
                len(dropped), ", ".join(dropped))
        _status(msg)


# --- Apply set submenu ---------------------------------------------------------
_apply_commands = {}  # set name -> FreeCAD command name
_menu_added = []      # command names already appended to the submenu
_workbench = None     # set by init_gui on Initialize/Activated


def _command_name_for(set_name):
    base = "VisibilitySets_ApplySet_" + "".join(
        c if c.isalnum() else "_" for c in set_name)
    name, n = base, 2
    taken = set(_apply_commands.values())
    while name in taken:
        name = "%s_%d" % (base, n)
        n += 1
    return name


def refresh_apply_menu(workbench=None):
    """(Re)scan the active document's saved sets and append any new ones to
    the 'Apply set' submenu. Called on workbench Initialize/Activated and
    after Save set. Appending only ever adds entries; a set deleted behind
    our back leaves an entry that reports the miss when clicked."""
    global _workbench
    if workbench is not None:
        _workbench = workbench
    wb = _workbench
    if wb is None:
        return
    names = []
    doc = App.ActiveDocument
    if doc is not None:
        mgr = store.get_manager(doc)
        if mgr is not None:
            names = store.list_sets(mgr)
    new_cmds = []
    for set_name in names:
        cmd = _apply_commands.get(set_name)
        if cmd is None:
            cmd = _command_name_for(set_name)
            Gui.addCommand(cmd, ApplySetCommand(set_name))
            _apply_commands[set_name] = cmd
        if cmd not in _menu_added:
            _menu_added.append(cmd)
            new_cmds.append(cmd)
    if new_cmds:
        wb.appendMenu(["Visibility Sets", "Apply set"], new_cmds)


_REGISTERED = False


def register():
    """Register the base commands (idempotent; per-set commands are added by
    refresh_apply_menu)."""
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True
    Gui.addCommand("VisibilitySets_Isolate", IsolateCommand())
    Gui.addCommand("VisibilitySets_TransparentOthers", TransparentOthersCommand())
    Gui.addCommand("VisibilitySets_Restore", RestoreCommand())
    Gui.addCommand("VisibilitySets_SaveSet", SaveSetCommand())
