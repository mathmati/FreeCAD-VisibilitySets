# FreeCAD VisibilitySets

Visibility Sets adds part isolation to FreeCAD: hide or fade everything
except the selected parts with one command, step back through view states
with a restore stack, and save named visibility sets that persist inside
the .FCStd file itself.

## Why

Three open FreeCAD issues ask for pieces of this. All three were still open
on 2026-07-18:

- [#12142](https://github.com/FreeCAD/FreeCAD/issues/12142) "Assembly:
  isolating a set of parts is tedious" (opened 2024-01; 5 reactions, 45
  comments as of 2026-07-18): in a large assembly you hide every other part
  to study how a few fit together, then toggle them all back by hand. The
  issue itself suggests the make-others-transparent option too.
- [#24753](https://github.com/FreeCAD/FreeCAD/issues/24753) (opened
  2025-10; 6 reactions, 13 comments as of 2026-07-18): isolate the
  selection with hide, wireframe, or transparency modes and a one-click
  restore. The author attached demo videos and the macro he uses, which
  says something about how far users will go to get this.
- [#11215](https://github.com/FreeCAD/FreeCAD/issues/11215) (opened
  2023-10): make the selected tree item temporarily visible in the 3D view
  even while it is hidden, for cycling through a tree without toggling
  every item by hand. A demo video linked from the issue shows the feature
  in realthunder's LinkStage3 fork.

What core FreeCAD 1.1 has today: a per-object Visibility toggle in the
tree, and that is all. No sets, no stack, no fade-the-rest.

## What it does (v1 scope)

Five commands in a small "Visibility Sets" workbench:

1. **Isolate selection**: hide everything except the selected objects.
   Containers are respected: the container chain above a selected object
   stays visible (hiding an `App::Part`, Body, or group hides its whole
   subtree), and the contents of a selected container keep their current
   state.
2. **Transparent others**: fade everything except the selection to 80%
   transparency instead of hiding it. The selection's containers and the
   contents of a selected container are not faded.
3. **Restore visibility**: pop the previous view state off the restore
   stack (newest first, capped at 10); if the stack is empty, show
   everything at 0% transparency.
4. **Save set...**: name the current visibility state. The set is stored in
   the document, so it survives saving and reopening the .FCStd, and
   survives being sent to someone else inside the file.
5. **Apply set** (submenu): apply a saved set. Objects created after the
   set was saved keep their current state; objects deleted since are
   dropped and reported by name, not treated as an error.

Isolate, Transparent others, and Apply set each push the current view state
onto the restore stack before changing anything, so Restore always has
somewhere to go. The stack is session-local: it is never written into the
document, so isolating parts does not dirty the file and no view snapshots
travel inside a .FCStd you share.

The named sets live in a "Visibility Sets" object in the tree (an
`App::FeaturePython` holding two JSON properties). It is plain document
data: no external files, no preferences database.

## How it is built

Three layers, split where FreeCAD's API forces the split:

- `freecad/VisibilitySets/core.py`: pure set algebra over name ->
  visibility maps. No FreeCAD imports.
- `freecad/VisibilitySets/store.py`: the persistent manager and the JSON
  (de)serialisation. App-side only, no GUI.
- `freecad/VisibilitySets/viewadapter.py` and `commands.py`: the GUI. The
  adapter only translates maps to real ViewObjects; it holds no logic.

The reason for the split: `ViewObject.Visibility` and
`ViewObject.Transparency` only exist while the GUI is loaded, so any logic
that touched them directly would be untestable in freecadcmd. With this
layout, everything except the final property writes runs headless.

## Verification method

Built and verified against a real installed FreeCAD 1.1.1
(1.1.1R20260414, bundled Python 3.11.14) on Windows 11:

- **Headless (`freecadcmd`)**: `verify/headless_regression.py` runs 21
  checks: the algebra (isolate/others/validate/cap, including the
  container-aware variants), named-set CRUD, restore-stack LIFO order and
  the 10-entry cap, the corrupt-JSON and wrong-shape guards, parent_map on
  a real document, and a .FCStd round-trip (objects plus manager saved,
  closed, reopened; the set still applies, the stack still pops, and an
  object deleted after the set was saved is dropped with a reported list).
  **21/21 checks pass** (latest run: FreeCAD 1.1.0, Linux); run log:
  `verify/out-headless.txt`. Two freecadcmd quirks shaped
  the run (scripts do not get `__name__ == "__main__"`, and print() output
  is unreliable); the wrapper that works around them is in
  `verify/README.md`.
- **GUI driver**: `verify/drivers/visibility_driver.py` drives the real
  command classes on real ViewObjects and captures screenshots.
  **UNVERIFIED**: written, never executed (no GUI session on the build
  machine). It is included so the GUI half is one command away from being
  checked, not as evidence.

One thing to be precise about, because it is the part most worth being
honest about: `ViewObject.Visibility` and `ViewObject.Transparency` are
outside FreeCAD's undo system, so Isolate, Transparent others, and Restore
do not appear in Edit > Undo. That is core FreeCAD behavior; I documented
it rather than faking transactions that would record nothing. The restore
stack is the undo path for view changes. Saving a named set changes a
document property, which is transactional, so Save set is undoable the
normal way.

## Requirements

FreeCAD 1.1+. No dependencies beyond what FreeCAD itself ships. Install by
copying or cloning this directory into FreeCAD's Mod directory (the usual
Addon Manager layout; `package.xml` is included).

## Known gaps (disclosed up front)

- Peek-on-hover (#11215) is not in v1. It needs a selection observer or an
  event filter on the tree view, a different mechanism from everything
  here. The named sets and the restore stack cover the persistent half of
  that request; the temporary half is future work.
- View changes are not in Edit > Undo (see "Verification method" above).
  Documented, not faked; the restore stack is the substitute.
- Wireframe-others mode from #24753 is not in v1; hide and transparency
  only.
- Saved sets record visibility, not transparency. The restore stack records
  both.
- There is no GUI command to delete a set in v1. The store supports it
  (`store.delete_set`, covered by the headless checks); the console is the
  way in for now.
- The Apply set submenu only grows within a session: entries for sets
  deleted behind its back remain until restart and report the miss when
  clicked.
- Only the headless half is verified. The GUI driver has never run, and the
  workbench/menu registration has not been exercised on a live install.
- Not internationalized (plain Python strings, no `QT_TRANSLATE_NOOP`).

## License

MIT, see `LICENSE`.

## Transparency

Built with AI assistance (Kimi Code CLI). Every verified claim above comes
from the recorded runs in `verify/`; anything not run is marked UNVERIFIED.
