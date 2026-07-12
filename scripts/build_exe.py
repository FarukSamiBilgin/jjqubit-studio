"""Windows .exe build script for JJQubit Studio (Task #6, final step).

Wraps PyInstaller with the project-specific options this app needs: the GUI
entry point, bundled example netlists, and hidden-import/collect-all hints
for scientific packages whose submodules PyInstaller's static import
analysis tends to miss (scqubits, qutip, h5py). Per docs/task.md Görev 6,
this is the LAST/hardest step -- a working ``python -m gui.app`` run comes
first; this script is expected to be iterated on as the other teammates'
modules land (new hidden imports, new data files).

Usage::

    python scripts/build_exe.py             # one-folder build under dist/
    python scripts/build_exe.py --onefile   # single .exe (slower to start)
    python scripts/build_exe.py --console   # keep console window (debugging)
    python scripts/build_exe.py --clean     # wipe build/ dist/ *.spec first

Requires ``pyinstaller`` (see requirements.txt); this script does not
install it for you.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = REPO_ROOT / "gui" / "app.py"
APP_NAME = "JJQubitStudio"

# Packages whose PyInstaller static import analysis misses submodules that
# are only imported dynamically/lazily (common for scientific packages with
# optional backends). --collect-all bundles a package's data files AND every
# submodule, which is the blunt-but-reliable fix for these.
COLLECT_ALL = [
    "scqubits",  # ships reference/cache data alongside code
    "qutip",     # backend-selected submodules picked at import time
]

HIDDEN_IMPORTS = [
    # h5py's HDF5 backend wiring is sometimes missed by static analysis
    # depending on the installed HDF5 build.
    "h5py.defs",
    "h5py.utils",
    "h5py._proxy",
]


def build(*, onefile: bool, clean: bool, windowed: bool) -> int:
    """Run PyInstaller for JJQubit Studio. Returns PyInstaller's exit code."""
    if not ENTRY_POINT.exists():
        print(f"error: entry point not found: {ENTRY_POINT}", file=sys.stderr)
        return 1

    if clean:
        for d in ("build", "dist"):
            shutil.rmtree(REPO_ROOT / d, ignore_errors=True)
        spec_file = REPO_ROOT / f"{APP_NAME}.spec"
        if spec_file.exists():
            spec_file.unlink()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(ENTRY_POINT),
        "--name",
        APP_NAME,
        "--noconfirm",
        "--paths",
        str(REPO_ROOT),
    ]
    if onefile:
        cmd.append("--onefile")
    if windowed:
        cmd.append("--windowed")  # no console window
    for pkg in COLLECT_ALL:
        cmd += ["--collect-all", pkg]
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]
    # Bundle the example netlists so a packaged app has something to open
    # on first run (see README.md "First run").
    examples_dir = REPO_ROOT / "examples"
    if examples_dir.exists():
        cmd += ["--add-data", f"{examples_dir}{os.pathsep}examples"]

    print("Running:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    """Parse CLI args and run the build; see module docstring for usage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single .exe file instead of a one-folder bundle "
        "(slower startup, easier to distribute).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove build/, dist/ and the .spec file before building.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep the console window open (useful when debugging a build; "
        "default is windowed, no console).",
    )
    args = parser.parse_args(argv)
    return build(onefile=args.onefile, clean=args.clean, windowed=not args.console)


if __name__ == "__main__":
    raise SystemExit(main())
