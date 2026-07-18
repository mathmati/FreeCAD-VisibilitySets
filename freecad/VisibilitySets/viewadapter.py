# SPDX-License-Identifier: MIT
"""freecad.VisibilitySets.viewadapter -- real ViewObjects (GUI only).

Thin translation layer between the pure name->state maps of ``core.py`` /
``store.py`` and ``ViewObject.Visibility`` / ``ViewObject.Transparency``.
No decisions live here: ``commands.py`` decides what to do, ``core.py``
computes the maps, this module only reads and writes view state. Importing
it without a GUI fails, by design (that is the whole reason the logic sits
in ``core.py``).
"""
from typing import Dict, List, Optional

import FreeCAD as App
import FreeCADGui as Gui  # noqa: F401  (import proves the GUI is loaded)

from . import core, store

#: Transparency used by transparent-others mode (0 = opaque, 100 = invisible).
DEFAULT_OTHER_TRANSPARENCY = 80


def _doc(doc=None):
    return doc if doc is not None else App.ActiveDocument


def _viewobject(obj):
    return getattr(obj, "ViewObject", None) if obj is not None else None


def current_names(doc=None) -> List[str]:
    """Sorted names of objects that have a view provider (the manager is
    excluded)."""
    doc = _doc(doc)
    return sorted(
        o.Name
        for o in doc.Objects
        if not store.is_manager_object(o) and _viewobject(o) is not None
    )


def snapshot(doc=None) -> Dict[str, Dict[str, object]]:
    """Full view state of the document: {"visibility": ..., "transparency": ...}.
    This is what gets pushed onto the restore stack before a command changes
    anything."""
    doc = _doc(doc)
    visibility: Dict[str, bool] = {}
    transparency: Dict[str, int] = {}
    for obj in doc.Objects:
        if store.is_manager_object(obj):
            continue
        vobj = _viewobject(obj)
        if vobj is None:
            continue
        visibility[obj.Name] = bool(vobj.Visibility)
        # Transparency exists only on geometry-capable view providers; the
        # base provider (groups, App::FeaturePython managers) lacks it.
        if hasattr(vobj, "Transparency"):
            transparency[obj.Name] = int(vobj.Transparency)
    return {"visibility": visibility, "transparency": transparency}


def apply_visibility(visibility_map: Dict[str, bool], doc=None) -> List[str]:
    """Write ViewObject.Visibility per the map. Names without a view provider
    are skipped; returns the names actually applied."""
    doc = _doc(doc)
    applied = []
    for name, visible in visibility_map.items():
        vobj = _viewobject(doc.getObject(name))
        if vobj is None:
            continue
        vobj.Visibility = bool(visible)
        applied.append(name)
    return applied


def apply_transparency(transparency_map: Dict[str, int], doc=None) -> List[str]:
    """Write ViewObject.Transparency per the map, clamped to 0..100."""
    doc = _doc(doc)
    applied = []
    for name, value in transparency_map.items():
        vobj = _viewobject(doc.getObject(name))
        if vobj is None or not hasattr(vobj, "Transparency"):
            continue
        vobj.Transparency = max(0, min(100, int(value)))
        applied.append(name)
    return applied


def apply_snapshot(snap: Dict[str, object], doc=None) -> None:
    """Restore a stack entry (both maps; a bare visibility map works too)."""
    snap = core.normalize_snapshot(snap)
    apply_visibility(snap["visibility"], doc)
    apply_transparency(snap["transparency"], doc)


def fade_others(
    selected_names: List[str],
    value: int = DEFAULT_OTHER_TRANSPARENCY,
    doc=None,
) -> List[str]:
    """Transparent-others mode: fade the complement of the selection to
    ``value`` percent. Visibility is untouched (faded objects stay visible);
    the selection keeps its own transparency. Returns the faded names."""
    doc = _doc(doc)
    faded = core.others(selected_names, current_names(doc))
    apply_transparency({name: value for name in faded}, doc)
    return faded
