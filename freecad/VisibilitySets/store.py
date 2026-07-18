# SPDX-License-Identifier: MIT
"""freecad.VisibilitySets.store -- document-side persistence, no GUI.

A manager is an ``App::FeaturePython`` object living in the document,
holding the named sets as a JSON String property, so a ``.FCStd``
save/load round-trips them. The restore stack is deliberately NOT stored
in the document: it is session-local (see the restore-stack section), so
using Isolate never dirties the file. The whole module works under
``freecadcmd`` where no ``ViewObject`` exists. The proxy class below is a shell: the module-level
functions do the work (the proxy delegates, FreeCAD convention), which
keeps them directly callable from tests and from ``commands.py``.
"""
import json
from typing import Dict, List, Optional, Tuple

import FreeCAD as App

from . import core

SCHEMA_VERSION = 1
DEFAULT_STACK_CAP = 10
MANAGER_NAME = "VisibilitySets"
PROXY_TYPE = "VisibilitySetsManager"


# --- JSON in String properties ----------------------------------------------
def _load_json(raw: str, what: str):
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise core.VisibilitySetError(
            "%s stored in the document is corrupt (%s); leaving it untouched"
            % (what, exc)
        )
    if not isinstance(data, dict):
        raise core.VisibilitySetError(
            "%s stored in the document is corrupt (top level is %s, expected "
            "an object); leaving it untouched" % (what, type(data).__name__)
        )
    return data


def _dump_json(data) -> str:
    # Deterministic output (sorted keys, small indent) keeps .FCStd diffs
    # readable when someone unzips one.
    return json.dumps(data, indent=1, sort_keys=True)


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise core.VisibilitySetError("a visibility set needs a non-empty name")
    return name


# --- named sets (CRUD) --------------------------------------------------------
def _read_sets(obj) -> Dict[str, dict]:
    data = _load_json(obj.SetsJson, "the named-sets data")
    if data is None:
        return {}
    sets = data.get("sets", {})
    if not isinstance(sets, dict):
        raise core.VisibilitySetError(
            "the named-sets data stored in the document is corrupt ('sets' is "
            "%s, expected an object); leaving it untouched" % type(sets).__name__
        )
    return dict(sets)


def _write_sets(obj, sets: Dict[str, dict]) -> None:
    obj.SetsJson = _dump_json({"version": SCHEMA_VERSION, "sets": sets})


def save_set(obj, name: str, visibility_map: Dict[str, bool]) -> None:
    """Create or overwrite the named set (overwrite is the update in CRUD)."""
    name = _clean_name(name)
    sets = _read_sets(obj)
    sets[name] = {
        "visibility": {str(k): bool(v) for k, v in visibility_map.items()}
    }
    _write_sets(obj, sets)


def get_set(obj, name: str) -> Optional[core.VisibilityMap]:
    """The stored visibility map, or None if no set has that name."""
    entry = _read_sets(obj).get(name)
    if entry is None:
        return None
    if not isinstance(entry, dict) or not isinstance(entry.get("visibility"), dict):
        raise core.VisibilitySetError(
            "the named-sets data stored in the document is corrupt (set %r "
            "has no visibility map); leaving it untouched" % name
        )
    return dict(entry["visibility"])


def list_sets(obj) -> List[str]:
    return sorted(_read_sets(obj))


def delete_set(obj, name: str) -> bool:
    """True if the set existed and was removed, False otherwise."""
    sets = _read_sets(obj)
    if name not in sets:
        return False
    del sets[name]
    _write_sets(obj, sets)
    return True


def resolve_set(
    obj, name: str, current_names: List[str]
) -> Tuple[core.VisibilityMap, List[str]]:
    """``(clean_map, dropped)`` for applying a saved set right now: names that
    vanished since the set was saved are dropped and reported, not an error."""
    saved = get_set(obj, name)
    if saved is None:
        raise core.VisibilitySetError("no visibility set named %r" % name)
    return core.validate_map(saved, current_names)


# --- restore stack -------------------------------------------------------------
# Session-local, keyed by document name: the stack is working view state,
# not model data. Persisting it in the document (the old StackJson design)
# meant every Isolate dirtied the file and shipped up to ten view-state
# snapshots inside any .FCStd passed to others. A stack now lives only for
# this FreeCAD session; a reopened document starts with an empty stack.
# Older documents may still carry a StackJson property on their manager
# object; it is ignored and never written again.
_session_stacks: Dict[str, List[dict]] = {}


def _doc_key(doc) -> str:
    name = getattr(doc, "Name", None)
    return name if name else str(id(doc))


def push_snapshot(doc, snapshot: Dict[str, object], label: str = "") -> None:
    """Push a snapshot (bare visibility map or full two-map form) onto the
    session stack for ``doc``, dropping the oldest entries beyond the cap.
    Does not touch or dirty the document."""
    entry = core.normalize_snapshot(snapshot)
    entry["label"] = str(label or "")
    key = _doc_key(doc)
    _session_stacks[key] = core.push_capped(
        _session_stacks.get(key, []), entry, DEFAULT_STACK_CAP)


def pop_snapshot(doc) -> Optional[dict]:
    """Pop the newest snapshot (full form, with ``label``), or None if empty."""
    stack = _session_stacks.get(_doc_key(doc), [])
    if not stack:
        return None
    return stack.pop()


def stack_depth(doc) -> int:
    return len(_session_stacks.get(_doc_key(doc), []))


def clear_stack(doc) -> None:
    _session_stacks.pop(_doc_key(doc), None)


# --- manager object lifecycle ---------------------------------------------------
def is_manager_object(obj) -> bool:
    """True for our manager, identified by its properties, not its proxy: the
    properties survive a document reload even if the proxy class fails to
    re-import, and the data is what matters."""
    return (
        obj.TypeId == "App::FeaturePython"
        and hasattr(obj, "SetsJson")
    )


def get_manager(doc):
    """The document's manager object, or None."""
    for obj in doc.Objects:
        if is_manager_object(obj):
            return obj
    return None


def get_or_create_manager(doc):
    """The document's manager, creating it on first use. One per document."""
    mgr = get_manager(doc)
    if mgr is None:
        mgr = doc.addObject("App::FeaturePython", MANAGER_NAME)
        mgr.Label = "Visibility Sets"
        VisibilitySetsManager(mgr)
    return mgr


def parent_map(doc) -> Dict[str, str]:
    """name -> immediate container name, for every object sitting inside an
    ``App::Part`` / Body (getParentGeoFeatureGroup) or a plain group
    (getParentGroup). Top-level objects are absent. Feeds the
    container-aware ``core.isolate_nested`` / ``core.others_nested``."""
    out: Dict[str, str] = {}
    for obj in doc.Objects:
        if is_manager_object(obj):
            continue
        parent = None
        try:
            parent = obj.getParentGeoFeatureGroup()
        except Exception:
            parent = None
        if parent is None:
            try:
                parent = obj.getParentGroup()
            except Exception:
                parent = None
        if parent is not None and parent.Name != obj.Name:
            out[obj.Name] = parent.Name
    return out


def collect_names(doc) -> List[str]:
    """Sorted names of everything visibility applies to (the manager itself
    is excluded)."""
    return sorted(o.Name for o in doc.Objects if not is_manager_object(o))


class VisibilitySetsManager(object):
    """FeaturePython proxy for the manager object.

    Holds no state of its own; every byte lives in the object's properties,
    so document save/load needs nothing more than the ``dumps``/``loads``
    pair below (FreeCAD 1.x prefers them; ``__getstate__``/``__setstate__``
    delegate for older callers). Methods delegate to the module functions.
    """

    def __init__(self, obj):
        obj.Proxy = self
        self.Type = PROXY_TYPE
        obj.addProperty(
            "App::PropertyString", "SetsJson", "VisibilitySets",
            "Named visibility sets (JSON, managed by the Visibility Sets addon).",
        )
        obj.setEditorMode("SetsJson", 2)   # hidden from the property editor

    # -- FreeCAD serialisation hooks --
    def dumps(self):
        return {"Type": PROXY_TYPE, "version": SCHEMA_VERSION}

    def loads(self, state):
        self.Type = PROXY_TYPE

    def __getstate__(self):
        return self.dumps()

    def __setstate__(self, state):
        self.loads(state)

    def onDocumentRestored(self, obj):
        pass

    def execute(self, obj):
        pass

    # -- delegates (FreeCAD passes the object explicitly) --
    def save_set(self, obj, name, visibility_map):
        return save_set(obj, name, visibility_map)

    def get_set(self, obj, name):
        return get_set(obj, name)

    def list_sets(self, obj):
        return list_sets(obj)

    def delete_set(self, obj, name):
        return delete_set(obj, name)

    def resolve_set(self, obj, name, current_names):
        return resolve_set(obj, name, current_names)

    def push_snapshot(self, doc, snapshot, label=""):
        return push_snapshot(doc, snapshot, label)

    def pop_snapshot(self, doc):
        return pop_snapshot(doc)

    def stack_depth(self, doc):
        return stack_depth(doc)

    def clear_stack(self, doc):
        return clear_stack(doc)
