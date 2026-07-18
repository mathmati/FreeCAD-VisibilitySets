# SPDX-License-Identifier: MIT
"""freecad.VisibilitySets.core -- pure visibility-set algebra.

No FreeCAD imports here on purpose: ``ViewObject.Visibility`` and
``ViewObject.Transparency`` only exist while the GUI is loaded, so every
piece of logic lives in this GUI-free module over plain ``name -> bool``
maps, where ``freecadcmd`` can test it headless. ``store.py`` (document
persistence) and ``viewadapter.py`` (real ViewObjects) are thin layers on
top and contain no logic of their own.
"""
from typing import Dict, Iterable, List, Tuple

#: name -> visible
VisibilityMap = Dict[str, bool]

#: what the restore stack stores: {"visibility": VisibilityMap,
#: "transparency": {name: int}, "label": str}
Snapshot = Dict[str, object]


class VisibilitySetError(ValueError):
    """Bad selection, unknown object name, or corrupt stored data."""


def _check_known(names: Iterable[str], all_names: Iterable[str], what: str) -> None:
    unknown = sorted(set(names) - set(all_names))
    if unknown:
        raise VisibilitySetError(
            "%s refer(s) to object(s) not in the document: %s"
            % (what, ", ".join(unknown))
        )


def isolate(selected_names: Iterable[str], all_names: Iterable[str]) -> VisibilityMap:
    """Return the map that shows exactly ``selected_names`` and hides the rest.

    Empty selections and names that are not in the document are errors: the
    caller almost certainly did not mean to hide everything.
    """
    selected = list(selected_names)
    if not selected:
        raise VisibilitySetError("isolate needs at least one selected object")
    _check_known(selected, all_names, "the selection")
    keep = set(selected)
    return {name: name in keep for name in all_names}


def others(selected_names: Iterable[str], all_names: Iterable[str]) -> List[str]:
    """Sorted complement of the selection: the objects that transparent-others
    mode fades (or that a caller could hide instead)."""
    _check_known(selected_names, all_names, "the selection")
    return sorted(set(all_names) - set(selected_names))


def _ancestors(name: str, parents: Dict[str, str]) -> List[str]:
    """Chain of containers above ``name`` per the ``parents`` map (immediate
    container first). Tolerates cycles: each container is visited once."""
    chain = []
    seen = set()
    cur = parents.get(name)
    while cur is not None and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        cur = parents.get(cur)
    return chain


def isolate_nested(
    selected_names: Iterable[str],
    all_names: Iterable[str],
    parents: Dict[str, str],
    current_visibility: Dict[str, bool] = None,
) -> VisibilityMap:
    """Container-aware isolate: show the selection, hide the rest.

    ``parents`` maps an object name to the name of its immediate container;
    top-level names are absent (see ``store.parent_map``). Hiding an
    ``App::Part``, Body, or group hides its whole subtree in the 3D view,
    so two refinements over plain ``isolate``: every ancestor container of
    a selected object stays visible (otherwise the selection itself would
    disappear), and objects inside a selected container keep their current
    visibility from ``current_visibility`` (default visible) instead of
    being force-hidden.
    """
    selected = list(selected_names)
    if not selected:
        raise VisibilitySetError("isolate needs at least one selected object")
    all_names = list(all_names)
    _check_known(selected, all_names, "the selection")
    selset = set(selected)
    keep = set(selected)
    for name in selected:
        keep.update(_ancestors(name, parents))
    current = dict(current_visibility or {})
    vmap = {}
    for name in all_names:
        if name in keep:
            vmap[name] = True
        elif any(a in selset for a in _ancestors(name, parents)):
            vmap[name] = bool(current.get(name, True))
        else:
            vmap[name] = False
    return vmap


def others_nested(
    selected_names: Iterable[str],
    all_names: Iterable[str],
    parents: Dict[str, str],
) -> List[str]:
    """Container-aware complement for transparent-others mode: ``others``
    minus the selection's ancestor containers and minus the contents of
    selected containers (fading either would fade the selection itself)."""
    selected = list(selected_names)
    all_names = list(all_names)
    _check_known(selected, all_names, "the selection")
    selset = set(selected)
    excluded = set(selected)
    for name in selected:
        excluded.update(_ancestors(name, parents))
    return sorted(
        name
        for name in all_names
        if name not in excluded
        and not any(a in selset for a in _ancestors(name, parents))
    )


def show_all(all_names: Iterable[str]) -> VisibilityMap:
    """Everything visible."""
    return {name: True for name in all_names}


def validate_map(
    visibility_map: Dict[str, bool], all_names: Iterable[str]
) -> Tuple[VisibilityMap, List[str]]:
    """Set-diff validation: restrict a saved map to names that still exist.

    Returns ``(clean_map, dropped)`` with ``dropped`` sorted. Names that
    vanished since the map was saved are dropped and reported, never an
    error; names that appeared since are simply not in the map (callers
    leave them as they are).
    """
    known = set(all_names)
    clean = {}
    dropped = []
    for name, visible in visibility_map.items():
        if name in known:
            clean[name] = bool(visible)
        else:
            dropped.append(name)
    return clean, sorted(dropped)


def normalize_snapshot(snapshot: Dict[str, object]) -> Snapshot:
    """Accept a bare visibility map or a full ``{"visibility", "transparency"}``
    dict; always return the full two-map form (``label`` added by the store).

    Ambiguity by design: a bare map with an object literally named
    "visibility" is read as the full form. Object names come from FreeCAD,
    which allows that name; do not name an object "visibility".
    """
    if "visibility" in snapshot or "transparency" in snapshot:
        return {
            "visibility": {
                str(k): bool(v)
                for k, v in dict(snapshot.get("visibility", {})).items()  # type: ignore[union-attr]
            },
            "transparency": {
                str(k): int(v)
                for k, v in dict(snapshot.get("transparency", {})).items()  # type: ignore[union-attr]
            },
        }
    return {
        "visibility": {str(k): bool(v) for k, v in snapshot.items()},
        "transparency": {},
    }


def push_capped(stack: List[Snapshot], entry: Snapshot, cap: int) -> List[Snapshot]:
    """Return a new stack with ``entry`` appended (newest last), the oldest
    entries dropped so the stack never exceeds ``cap``. A cap below 1 means
    "keep nothing"."""
    if cap < 1:
        return []
    return (list(stack) + [entry])[-cap:]
