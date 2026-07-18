# Visibility Sets `verify/`: how to run

This tree backs the "Verification method" section of the README:

1. **Headless (`freecadcmd`)**: `headless_regression.py` covers everything
   that can exist without a GUI: the pure algebra of `core.py`, the
   document-side store (named-set CRUD, restore stack), the corrupt-JSON
   guard, and a real `.FCStd` save/close/reopen round-trip. **17 checks.**
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

Green means a final `17/17 checks pass` line plus `SYSTEM_EXIT code=0`.
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
| store: manager singleton, named-set CRUD | 7-10 |
| store: restore stack LIFO, cap 10, empty pop | 11-13 |
| store: corrupt-JSON guard, resolve_set errors | 14-15 |
| .FCStd: sets + stack + proxy class survive save/close/reopen | 16 |
| .FCStd: object deleted after saving is dropped and reported | 17 |
| real commands on real ViewObjects | `drivers/visibility_driver.py` (UNVERIFIED) |

If the headless count ever stops being 17, update both the script's
`EXPECTED_CHECKS` and the README's "17/17 checks pass" line. Keeping them
pinned together is the whole point.
