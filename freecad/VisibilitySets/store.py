# SPDX-License-Identifier: MIT
"""freecad.VisibilitySets.store -- document-side persistence, no GUI.

A manager is an ``App::FeaturePython`` object living in the document,
holding two JSON String properties (named sets, restore stack) plus the
stack cap. Because it is App-side, a ``.FCStd`` save/load round-trips
everything, and the whole module works under ``freecadcmd`` where no
``ViewObject`` exists. The proxy class below is a shell: the module-level
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
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise core.VisibilitySetError(
            "%s stored in the document is corrupt (%s); leaving it untouched"
            % (what, exc)
        )


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
    return {} if data is None else dict(data.get("sets", {}))


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
    return None if entry is None else dict(entry["visibility"])


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
def _read_stack(obj) -> List[dict]:
    data = _load_json(obj.StackJson, "the restore-stack data")
    return [] if data is None else list(data.get("stack", []))


def _write_stack(obj, stack: List[dict]) -> None:
    obj.StackJson = _dump_json({"version": SCHEMA_VERSION, "stack": stack})


def _cap(obj) -> int:
    try:
        cap = int(getattr(obj, "StackCap", DEFAULT_STACK_CAP))
    except (TypeError, ValueError):
        cap = DEFAULT_STACK_CAP
    return max(cap, 1)


def push_snapshot(obj, snapshot: Dict[str, object], label: str = "") -> None:
    """Push a snapshot (bare visibility map or full two-map form), dropping
    the oldest entries beyond the cap."""
    entry = core.normalize_snapshot(snapshot)
    entry["label"] = str(label or "")
    _write_stack(obj, core.push_capped(_read_stack(obj), entry, _cap(obj)))


def pop_snapshot(obj) -> Optional[dict]:
    """Pop the newest snapshot (full form, with ``label``), or None if empty."""
    stack = _read_stack(obj)
    if not stack:
        return None
    entry = stack.pop()
    _write_stack(obj, stack)
    return entry


def stack_depth(obj) -> int:
    return len(_read_stack(obj))


def clear_stack(obj) -> None:
    _write_stack(obj, [])


# --- manager object lifecycle ---------------------------------------------------
def is_manager_object(obj) -> bool:
    """True for our manager, identified by its properties, not its proxy: the
    properties survive a document reload even if the proxy class fails to
    re-import, and the data is what matters."""
    return (
        obj.TypeId == "App::FeaturePython"
        and hasattr(obj, "SetsJson")
        and hasattr(obj, "StackJson")
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
        obj.addProperty(
            "App::PropertyString", "StackJson", "VisibilitySets",
            "Restore stack (JSON, managed by the Visibility Sets addon).",
        )
        obj.addProperty(
            "App::PropertyInteger", "StackCap", "VisibilitySets",
            "Maximum restore-stack depth.",
        )
        obj.StackCap = DEFAULT_STACK_CAP
        obj.setEditorMode("SetsJson", 2)   # hidden from the property editor
        obj.setEditorMode("StackJson", 2)  # hidden
        obj.setEditorMode("StackCap", 1)   # read-only

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

    def push_snapshot(self, obj, snapshot, label=""):
        return push_snapshot(obj, snapshot, label)

    def pop_snapshot(self, obj):
        return pop_snapshot(obj)

    def stack_depth(self, obj):
        return stack_depth(obj)

    def clear_stack(self, obj):
        return clear_stack(obj)
