# JJQubit Studio — Windows Installer (Inno Setup)

This directory contains the [Inno Setup](https://jrsoftware.org/isinfo.php)
script `JJQubitStudio.iss`, which packages the app's PyInstaller
**one-folder** build into a single Windows setup `.exe`.

The installer does **not** build the app; it only wraps an already-built
`dist\JJQubitStudio\` folder. So the flow is always: build first, then compile
the installer.

## 1. Build the app

From the **repository root** (not this folder), produce the one-folder build:

```powershell
python scripts\build_exe.py --clean
```

This creates `dist\JJQubitStudio\`, containing `JJQubitStudio.exe` and its
`_internal\` support tree (Qt plugins, bundled `examples\`, and the
`scqubits`/`qutip`/`h5py` data the app needs). The installer script packages
this entire folder.

If `dist\JJQubitStudio\` is missing, compiling the installer fails with a
"no files found" error — that's the intended guard. Re-run the build.

## 2. Install Inno Setup

Download and install Inno Setup 6 or newer from the official site:

- https://jrsoftware.org/isdl.php

The compiler is `iscc.exe` (typically at
`C:\Program Files (x86)\Inno Setup 6\ISCC.exe`); add it to `PATH` or call it
with its full path.

## 3. Compile the installer

From the repository root:

```powershell
iscc scripts\installer\JJQubitStudio.iss
```

Or open `scripts\installer\JJQubitStudio.iss` in the **Inno Setup Compiler**
GUI and press **F9** (Build → Compile).

## 4. Output

The compiled setup executable is written to the `Output\` directory next to
the `.iss` script (i.e. `scripts\installer\Output\`), named:

```
JJQubitStudioSetup-<version>.exe
```

for example `JJQubitStudioSetup-0.1.0.exe`. Hand this single file to end users;
running it installs JJQubit Studio to `Program Files\JJQubit Studio`, adds a
Start Menu shortcut (and an optional desktop shortcut), and registers an
uninstaller in *Apps & features*.

## Version syncing

`JJQubitStudio.iss` defines `MyAppVersion` (the installer's `AppVersion` and
the output file name). This value must match `APP_VERSION` in
[`gui/app.py`](../../gui/app.py) (currently `"0.1.0"`). There is no automatic
coupling — when you bump the app version, update **both** places.

The app name and executable name in the script likewise mirror `gui/app.py`
(`APP_NAME = "JJQubit Studio"`) and the PyInstaller build
(`JJQubitStudio.exe`, from `scripts/build_exe.py` / `JJQubitStudio.spec`).

## Notes

- No `LicenseFile` is configured because the repository currently has no
  `LICENSE` file. If one is added at the repo root, uncomment the `LicenseFile`
  line in `JJQubitStudio.iss` to show it during installation.
- The installer packages the **one-folder** build. The `--onefile` PyInstaller
  variant produces a single self-contained `.exe` that needs no installer at
  all; use whichever distribution path suits you (see
  `docs/site/packaging.md`).
