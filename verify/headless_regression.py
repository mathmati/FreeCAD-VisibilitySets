# VERIFIED 2026-07-18: 21/21 checks pass on FreeCAD 1.1.0 (Linux, conda
# build); the earlier 17-check version also passed on FreeCAD 1.1.1
# (1.1.1R20260414), bundled Python 3.11.14, Windows 11. Run log:
# verify/out-headless.txt.
# SPDX-License-Identifier: MIT
"""verify/headless_regression.py -- Visibility Sets headless regression.

Run from the repo root with freecadcmd. Two quirks of freecadcmd 1.1.1 on
Windows shaped how: scripts passed on the command line do NOT get
``__name__ == "__main__"`` and their print() output is unreliable, so the
run goes through a small ``-c`` wrapper that redirects stdout/stderr to a
file and exec()s this script with a proper ``__name__`` (the exact wrapper
is in verify/README.md). The log lands in ``verify/out-headless.txt``.

What this covers (everything except the GUI translation layer, which cannot
exist without a GUI; see verify/drivers/visibility_driver.py, UNVERIFIED):

   core algebra   1-8    isolate / others / validate_map / push_capped,
                         plus the container-aware isolate_nested /
                         others_nested
   store, 1 doc   9-17   manager singleton, named-set CRUD, restore stack
                         (LIFO, cap 10, empty pop), corrupt-JSON guard,
                         resolve_set errors
   store, shapes  18-19  wrong-shape JSON guard, parent_map on a real
                         document (App::Part chain plus a plain group)
   .FCStd         20-21  sets + stack + proxy class survive
                         saveAs/close/openDocument, and a set referencing
                         an object deleted after saving drops it with a
                         reported list instead of failing

Checks 9-17 share one document and one manager on purpose (they read as one
continuous session, exactly like a user's); checks 20-21 use a second
document that is saved, closed, and reopened.
"""
import os
import sys
import traceback

# --- make the workbench importable from a source checkout ------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_TMP_DIR = os.path.join(_HERE, "tmp")
try:
    import freecad  # FreeCAD's own namespace package (present under freecadcmd)
    freecad.__path__ = [os.path.join(_REPO_ROOT, "freecad")] + list(freecad.__path__)
except ImportError:  # extremely defensive: fall back to plain sys.path
    sys.path.insert(0, _REPO_ROOT)

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402  # makes Part::* types creatable

from freecad.VisibilitySets import core, store  # noqa: E402

EXPECTED_CHECKS = 21

_checks = []


def check(name):
    def deco(fn):
        _checks.append((name, fn))
        return fn
    return deco


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def raises(exc_type, fn, needle=None):
    """fn() must raise exc_type (whose message must contain needle)."""
    try:
        fn()
    except exc_type as exc:
        if needle is not None and needle not in str(exc):
            raise AssertionError("error %r does not contain %r" % (exc, needle))
        return
    raise AssertionError("expected %s, nothing raised" % exc_type.__name__)


# --- shared fixture ---------------------------------------------------------
class Fixture(object):
    """doc1: live session for checks 7-15. doc2: the save/close/reopen one."""

    def __init__(self):
        self.doc1 = App.newDocument("VisSetsMain")
        self.doc1.addObject("Part::Box", "Widget")
        self.doc1.addObject("Part::Cylinder", "Bolt")
        self.mgr = store.get_or_create_manager(self.doc1)

        self.doc2 = App.newDocument("VisSetsRoundTrip")
        self.assembly = self.doc2.addObject("App::Part", "Assembly")
        self.bracket = self.doc2.addObject("Part::Box", "Bracket")
        self.pin = self.doc2.addObject("Part::Cylinder", "Pin")
        self.assembly.addObject(self.bracket)
        self.assembly.addObject(self.pin)
        self.ball = self.doc2.addObject("Part::Sphere", "Ball")
        self.doc2.recompute()


# --- 1-6: core algebra --------------------------------------------------------
@check("core.isolate: selected stay visible, everything else hidden")
def c01(fx):
    vmap = core.isolate(["Widget"], ["Widget", "Bolt", "Nut"])
    ok(vmap == {"Widget": True, "Bolt": False, "Nut": False},
       "unexpected isolate map: %r" % vmap)


@check("core.isolate: an empty selection is an error, not 'hide everything'")
def c02(fx):
    raises(core.VisibilitySetError,
           lambda: core.isolate([], ["Widget"]), "at least one")


@check("core.isolate: a selected name not in the document is an error")
def c03(fx):
    raises(core.VisibilitySetError,
           lambda: core.isolate(["Widget", "Ghost"], ["Widget"]), "Ghost")


@check("core.others: sorted complement of the selection, unknown names error")
def c04(fx):
    ok(core.others(["Bolt"], ["Widget", "Bolt", "Nut"]) == ["Nut", "Widget"],
       "unexpected complement: %r" % core.others(["Bolt"], ["Widget", "Bolt", "Nut"]))
    raises(core.VisibilitySetError,
           lambda: core.others(["Ghost"], ["Widget"]), "Ghost")


@check("core.validate_map: vanished names dropped and reported, never an error")
def c05(fx):
    clean, dropped = core.validate_map(
        {"Widget": True, "Ghost2": False, "Bolt": 1, "Ghost1": True},
        ["Widget", "Bolt"])
    ok(clean == {"Widget": True, "Bolt": True},
       "unexpected clean map: %r" % clean)
    ok(dropped == ["Ghost1", "Ghost2"], "dropped not sorted: %r" % dropped)


@check("core.push_capped: stack never exceeds the cap, oldest dropped first")
def c06(fx):
    stack = []
    for i in range(1, 13):
        stack = core.push_capped(stack, {"n": i}, 10)
    ok(len(stack) == 10, "stack length is %d" % len(stack))
    ok(stack[0]["n"] == 3 and stack[-1]["n"] == 12,
       "wrong survivors: %r" % [e["n"] for e in stack])
    ok(core.push_capped([{"n": 1}], {"n": 2}, 0) == [], "cap 0 keeps entries")


@check("core.isolate_nested: ancestors stay visible, selected container's contents keep state")
def c06b(fx):
    parents = {"Sub": "Asm", "Box": "Sub", "Pin": "Asm"}
    all_names = ["Asm", "Sub", "Box", "Pin", "Loose"]
    # Selecting a deep child keeps its whole container chain visible.
    vmap = core.isolate_nested(["Box"], all_names, parents, {"Loose": True})
    ok(vmap == {"Asm": True, "Sub": True, "Box": True,
                "Pin": False, "Loose": False},
       "deep-child isolate map: %r" % vmap)
    # Selecting a container preserves its contents' current visibility
    # (a hidden child stays hidden), so container round-trips hold.
    vmap = core.isolate_nested(["Sub"], all_names, parents, {"Box": False})
    ok(vmap == {"Asm": True, "Sub": True, "Box": False,
                "Pin": False, "Loose": False},
       "container isolate map: %r" % vmap)
    raises(core.VisibilitySetError,
           lambda: core.isolate_nested([], all_names, parents), "at least one")


@check("core.others_nested: complement excludes the selection's containers and contents")
def c06c(fx):
    parents = {"Sub": "Asm", "Box": "Sub", "Pin": "Asm"}
    all_names = ["Asm", "Sub", "Box", "Pin", "Loose"]
    ok(core.others_nested(["Box"], all_names, parents) == ["Loose", "Pin"],
       "deep-child complement: %r"
       % core.others_nested(["Box"], all_names, parents))
    ok(core.others_nested(["Sub"], all_names, parents) == ["Loose", "Pin"],
       "container complement: %r"
       % core.others_nested(["Sub"], all_names, parents))
    raises(core.VisibilitySetError,
           lambda: core.others_nested(["Ghost"], all_names, parents), "Ghost")


# --- 9-17: store on one live document -----------------------------------------
@check("store: one manager per document; collect_names excludes it")
def c07(fx):
    again = store.get_or_create_manager(fx.doc1)
    ok(again.Name == fx.mgr.Name, "a second manager object was created")
    ok(fx.mgr.TypeId == "App::FeaturePython", "TypeId is %s" % fx.mgr.TypeId)
    names = store.collect_names(fx.doc1)
    ok(names == ["Bolt", "Widget"], "collect_names: %r" % names)


@check("store: save_set/get_set round-trip; list_sets is sorted")
def c08(fx):
    store.save_set(fx.mgr, "beta", {"Widget": True, "Bolt": True})
    store.save_set(fx.mgr, "alpha", {"Widget": True, "Bolt": False})
    ok(store.get_set(fx.mgr, "alpha") == {"Widget": True, "Bolt": False},
       "get_set: %r" % store.get_set(fx.mgr, "alpha"))
    ok(store.list_sets(fx.mgr) == ["alpha", "beta"],
       "list_sets: %r" % store.list_sets(fx.mgr))


@check("store: saving over an existing name overwrites it (update in CRUD)")
def c09(fx):
    store.save_set(fx.mgr, "alpha", {"Widget": False})
    ok(store.get_set(fx.mgr, "alpha") == {"Widget": False},
       "overwrite did not stick: %r" % store.get_set(fx.mgr, "alpha"))
    ok(store.list_sets(fx.mgr) == ["alpha", "beta"], "set count changed on update")


@check("store: delete_set reports True/False honestly; get_set then returns None")
def c10(fx):
    ok(store.delete_set(fx.mgr, "beta") is True, "delete of existing set not True")
    ok(store.delete_set(fx.mgr, "beta") is False, "second delete not False")
    ok(store.get_set(fx.mgr, "beta") is None, "deleted set still readable")


@check("store: restore stack is LIFO and snapshots normalize to the full form")
def c11(fx):
    store.push_snapshot(fx.mgr, {"Widget": True}, label="first")
    store.push_snapshot(fx.mgr,
                        {"visibility": {"Widget": False},
                         "transparency": {"Widget": 80}},
                        label="second")
    top = store.pop_snapshot(fx.mgr)
    ok(top["label"] == "second", "popped %r first" % top["label"])
    ok(top["visibility"] == {"Widget": False} and top["transparency"] == {"Widget": 80},
       "full-form snapshot mangled: %r" % top)
    nxt = store.pop_snapshot(fx.mgr)
    ok(nxt["label"] == "first" and nxt["transparency"] == {},
       "bare map did not normalize: %r" % nxt)


@check("store: stack capped at 10 over 12 pushes, popping newest first")
def c12(fx):
    for i in range(1, 13):
        store.push_snapshot(fx.mgr, {"Widget": True}, label="s%d" % i)
    ok(store.stack_depth(fx.mgr) == 10, "depth is %d" % store.stack_depth(fx.mgr))
    labels = []
    while True:
        entry = store.pop_snapshot(fx.mgr)
        if entry is None:
            break
        labels.append(entry["label"])
    ok(labels == ["s%d" % i for i in range(12, 2, -1)],
       "pop order: %r" % labels)


@check("store: popping an empty stack returns None")
def c13(fx):
    ok(store.stack_depth(fx.mgr) == 0, "stack not drained before this check")
    ok(store.pop_snapshot(fx.mgr) is None, "empty pop not None")


@check("store: corrupt JSON in the document raises a clear error, not a raw one")
def c14(fx):
    stash = fx.mgr.SetsJson
    try:
        fx.mgr.SetsJson = "{not valid json"
        raises(core.VisibilitySetError,
               lambda: store.get_set(fx.mgr, "alpha"), "corrupt")
    finally:
        fx.mgr.SetsJson = stash
    ok(store.get_set(fx.mgr, "alpha") == {"Widget": False},
       "sets data did not survive the corrupt-JSON check")


@check("store: resolve_set on a missing set (and a blank set name) errors clearly")
def c15(fx):
    raises(core.VisibilitySetError,
           lambda: store.resolve_set(fx.mgr, "no-such-set", ["Widget"]),
           "no visibility set named")
    raises(core.VisibilitySetError,
           lambda: store.save_set(fx.mgr, "   ", {"Widget": True}),
           "non-empty name")


@check("store: valid JSON of the wrong shape raises the corrupt-data error, not a raw one")
def c15b(fx):
    stash_sets = fx.mgr.SetsJson
    stash_stack = fx.mgr.StackJson
    try:
        fx.mgr.SetsJson = "[1, 2]"
        raises(core.VisibilitySetError,
               lambda: store.get_set(fx.mgr, "alpha"), "corrupt")
        fx.mgr.SetsJson = '{"version": 1, "sets": []}'
        raises(core.VisibilitySetError,
               lambda: store.list_sets(fx.mgr), "corrupt")
        fx.mgr.SetsJson = '{"version": 1, "sets": {"weird": {}}}'
        raises(core.VisibilitySetError,
               lambda: store.get_set(fx.mgr, "weird"), "corrupt")
        fx.mgr.StackJson = '"hello"'
        raises(core.VisibilitySetError,
               lambda: store.stack_depth(fx.mgr), "corrupt")
    finally:
        fx.mgr.SetsJson = stash_sets
        fx.mgr.StackJson = stash_stack
    ok(store.get_set(fx.mgr, "alpha") == {"Widget": False},
       "sets data did not survive the shape-guard check")


@check("store.parent_map: App::Part chains and plain groups on a real document")
def c15c(fx):
    doc = App.newDocument("VisSetsParents")
    try:
        asm = doc.addObject("App::Part", "Asm")
        sub = doc.addObject("App::Part", "Sub")
        box = doc.addObject("Part::Box", "Box")
        grp = doc.addObject("App::DocumentObjectGroup", "Grp")
        ball = doc.addObject("Part::Sphere", "Ball")
        doc.addObject("Part::Box", "Loose")
        asm.addObject(sub)
        sub.addObject(box)
        grp.addObject(ball)
        pm = store.parent_map(doc)
        # App::Part auto-creates Origin/axis/plane children; they map to
        # their Part too, but only the objects this check placed matter.
        placed = {k: v for k, v in pm.items()
                  if k in ("Asm", "Sub", "Box", "Grp", "Ball", "Loose")}
        ok(placed == {"Sub": "Asm", "Box": "Sub", "Ball": "Grp"},
           "parent_map: %r" % placed)
    finally:
        App.closeDocument(doc.Name)


# --- 20-21: .FCStd persistence -------------------------------------------------
@check("fcstd: sets, stack, and the proxy class survive save/close/reopen")
def c16(fx):
    mgr2 = store.get_or_create_manager(fx.doc2)
    saved = {"Assembly": True, "Ball": False, "Bracket": True, "Pin": False}
    store.save_set(mgr2, "fasteners", saved)
    store.push_snapshot(mgr2, {"Assembly": True}, label="before save 1")
    store.push_snapshot(mgr2, {"Assembly": False}, label="before save 2")

    os.makedirs(_TMP_DIR, exist_ok=True)
    fx.path = os.path.join(_TMP_DIR, "visibilitysets_roundtrip.FCStd")
    if os.path.exists(fx.path):
        os.remove(fx.path)
    fx.doc2.saveAs(fx.path)
    App.closeDocument(fx.doc2.Name)

    fx.doc2 = App.openDocument(fx.path)
    ok(fx.doc2 is not None, "openDocument returned None")
    mgr2 = store.get_manager(fx.doc2)
    ok(mgr2 is not None, "manager object missing after reload")
    ok(isinstance(mgr2.Proxy, store.VisibilitySetsManager),
       "proxy class did not restore (got %r)" % type(mgr2.Proxy))
    ok(store.get_set(mgr2, "fasteners") == saved,
       "set mangled by round-trip: %r" % store.get_set(mgr2, "fasteners"))
    ok(store.stack_depth(mgr2) == 2,
       "stack depth after reload: %d" % store.stack_depth(mgr2))
    top = store.pop_snapshot(mgr2)
    ok(top["label"] == "before save 2", "stack order broke on reload: %r" % top)
    ok(store.stack_depth(mgr2) == 1, "pop on restored stack failed")
    fx.mgr2 = mgr2


@check("fcstd: after reload, an object deleted since the set was saved is dropped and reported")
def c17(fx):
    fx.doc2.removeObject("Pin")
    names = store.collect_names(fx.doc2)
    ok("Pin" not in names, "Pin still present after removeObject")
    clean, dropped = store.resolve_set(fx.mgr2, "fasteners", names)
    ok(dropped == ["Pin"], "dropped list: %r" % dropped)
    ok(clean == {"Assembly": True, "Ball": False, "Bracket": True},
       "resolved map: %r" % clean)
    ok("Pin" in store.get_set(fx.mgr2, "fasteners"),
       "the stored set itself was modified by resolve_set")


def main():
    fx = Fixture()
    passed = 0
    failures = []
    for idx, (name, fn) in enumerate(_checks, 1):
        try:
            fn(fx)
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures.append((idx, name, exc))
            print("[FAIL %2d] %s" % (idx, name))
            traceback.print_exc()
        else:
            passed += 1
            print("[ ok  %2d] %s" % (idx, name))
    for doc in (fx.doc1, fx.doc2):
        try:
            App.closeDocument(doc.Name)
        except Exception:
            pass
    total = passed + len(failures)
    print("-" * 64)
    print("%d/%d checks pass" % (passed, total))
    if total != EXPECTED_CHECKS:
        print("WARNING: ran %d checks, expected %d -- update EXPECTED_CHECKS"
              % (total, EXPECTED_CHECKS))
    if failures:
        print("FAILURES:")
        for idx, name, exc in failures:
            print("  %2d. %s: %s" % (idx, name, exc))
        return 1
    return 0


# Not guarded by __name__ == "__main__": stock freecadcmd (for example the
# conda-forge 1.1.0 build) does not set __name__ that way, so a guarded
# harness silently runs zero checks and still exits 0. Run unconditionally;
# os._exit propagates the code without tripping freecadcmd's SystemExit
# handling, and the flush beats freecadcmd's buffered stdout.
rc = main()
sys.stdout.flush()
os._exit(rc)
