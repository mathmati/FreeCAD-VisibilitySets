# Visibility Sets `verify/`: how to run

This tree backs the "Verification method" section of the README:

1. **Headless (`freecadcmd`)**: `headless_regression.py` covers everything
   that can exist without a GUI: the pure algebra of `core.py`, the
   document-side store (named-set CRUD, restore stack), the corrupt-JSON
   guard, and a real `.FCStd` save/close/reopen round-trip. **21 checks.**
2. **GUI driver**: `drivers/visibility_driver.py` drives the real command
   classes against real ViewObjects on a sample assembly and captures
   screenshots. **UNVERIFIED as of 2026-07-18**: written, never executed
   (no GUI session on the build machine). Run it before trusting it.

## Requirements

- FreeCAD 1.1+ (`freecadcmd` for the headless run, `freecad` for the driver)
- No third-party Python packages.

## Run (headless)

Two quirks of `freecadcmd` 1.1.1 on Windows shaped this: a script passed on
the command line does not get `__name__ == "__main__"`, and its print()
output is unreliable. Run it through this wrapper, which redirects
stdout/stderr to a file and exec()s the script properly:

```bash
FC="/c/Users/matle/AppData/Local/Programs/FreeCAD 1.1/bin/freecadcmd.exe"
P="$(pwd -W)/verify/headless_regression.py"; O="$(pwd -W)/verify/out-headless.txt"
"$FC" -c "
import sys,traceback
_f=open(r'$O','w',buffering=1); sys.stdout=_f; sys.stderr=_f
try:
    exec(compile(open(r'$P').read(), r'$P', 'exec'), {'__name__':'__main__','__file__':r'$P'})
except SystemExit as e: print('SYSTEM_EXIT code=%r' % (e.code,))
except BaseException: traceback.print_exc()
_f.flush()" > /dev/null 2>&1
cat "$O"
```

Green means a final `21/21 checks pass` line plus `SYSTEM_EXIT code=0`.
(Also: freecadcmd's bundled Python is a Windows build and does not
understand Git-Bash paths like /tmp; the script keeps its temp `.FCStd`
under `verify/tmp/` for that reason.)

## Run (GUI driver, UNVERIFIED)

```bash
freecad verify/drivers/visibility_driver.py
```

Prints `PASS`/`FAIL` per stage, writes the verdict to
`verify/out/visibility_driver.result.txt` (grep that file; GUI startup
scripts do not reliably propagate exit codes), and drops screenshots in
`verify/out/`.

## Check inventory

| Area | Checks |
|---|---|
| core: isolate / others / validate_map / push_capped | 1-6 |
| core: container-aware isolate_nested / others_nested | 7-8 |
| store: manager singleton, named-set CRUD | 9-12 |
| store: restore stack LIFO, cap 10, empty pop | 13-15 |
| store: corrupt-JSON guard, resolve_set errors | 16-17 |
| store: wrong-shape JSON guard; parent_map on a real document | 18-19 |
| .FCStd: sets + stack + proxy class survive save/close/reopen | 20 |
| .FCStd: object deleted after saving is dropped and reported | 21 |
| real commands on real ViewObjects | `drivers/visibility_driver.py` (UNVERIFIED) |

If the headless count ever stops being 21, update both the script's
`EXPECTED_CHECKS` and the README's "21/21 checks pass" line. Keeping them
pinned together is the whole point.
