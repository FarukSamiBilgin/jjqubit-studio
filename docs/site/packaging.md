# Packaging & Distribution

JJQubit Studio ships as a standalone Windows application — no Python
installation required on the end user's machine. There are two distribution
paths, both built from the same PyInstaller bundle:

1. A **PyInstaller build** (a one-folder directory or a single `.exe`), for
   quick hand-off or a portable copy.
2. A **Windows installer** (`Setup.exe`, built with Inno Setup) that installs
   into *Program Files*, adds Start Menu / desktop shortcuts, and registers an
   uninstaller.

The installer wraps the one-folder PyInstaller build, so you always build with
PyInstaller first.

```
gui/app.py  --(PyInstaller)-->  dist\JJQubitStudio\  --(Inno Setup)-->  JJQubitStudioSetup-<version>.exe
```

## 1. PyInstaller build

The build is driven by `scripts/build_exe.py`, which wraps PyInstaller with the
project-specific options the app needs (GUI entry point `gui/app.py`, bundled
`examples\`, and `--collect-all` / hidden-import hints for `scqubits`, `qutip`,
and `h5py`, whose submodules PyInstaller's static analysis tends to miss).

From the repository root:

```powershell
python scripts\build_exe.py --clean
```

This produces the **one-folder** build `dist\JJQubitStudio\`, containing
`JJQubitStudio.exe` alongside an `_internal\` support tree. Distribute the whole
folder; the user runs `JJQubitStudio.exe`.

Useful flags:

| Flag        | Effect                                                            |
| ----------- | ---------------------------------------------------------------- |
| `--clean`   | Remove `build/`, `dist/`, and the generated `.spec` first.       |
| `--onefile` | Emit a single self-contained `.exe` (slower to start, easiest to hand someone) instead of a one-folder bundle. |
| `--console` | Keep the console window open (for debugging a broken build; default is windowed / no console). |

The **one-folder** build starts faster and is what the Windows installer
packages. The **`--onefile`** build is a single portable `.exe` that needs no
installer — good for a quick share, at the cost of slower startup (it unpacks
to a temp directory on each launch).

Requirements: `pyinstaller` must be installed in the active environment (it is
pinned in `requirements.txt`); the build script does not install it for you.

## 2. Windows installer (Inno Setup)

The installer definition lives in `scripts/installer/JJQubitStudio.iss` and is
compiled with [Inno Setup](https://jrsoftware.org/isinfo.php). It packages the
entire `dist\JJQubitStudio\` one-folder build, so run the PyInstaller build
(above) **first**.

Steps:

1. Build `dist\JJQubitStudio\` with `python scripts\build_exe.py --clean`.
2. Install Inno Setup 6+ from <https://jrsoftware.org/isdl.php>.
3. Compile the script:

   ```powershell
   iscc scripts\installer\JJQubitStudio.iss
   ```

   (or open the `.iss` in the Inno Setup Compiler GUI and press **F9**).
4. The setup executable appears in `scripts\installer\Output\` as
   `JJQubitStudioSetup-<version>.exe`.

What the installer does:

- Installs to `Program Files\JJQubit Studio` (`{autopf}\JJQubit Studio`).
- Creates a Start Menu shortcut, plus an **optional** desktop shortcut
  (unchecked by default).
- Registers an uninstaller in *Apps & features*.
- Requires administrator rights (installing under *Program Files*).

See `scripts/installer/README.md` for the detailed, step-by-step build/compile
guide.

## Version management

The app version is defined once in code, as `APP_VERSION` in `gui/app.py`
(currently `0.1.0`). The installer script mirrors it in its `MyAppVersion`
define, which sets the installer's `AppVersion` and the output file name.
There is no automatic coupling between the two — **update both together** when
cutting a release. The app name (`JJQubit Studio`) and executable name
(`JJQubitStudio.exe`) likewise come from `gui/app.py` (`APP_NAME`) and the
PyInstaller build.
