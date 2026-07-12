"""JJQubit Studio GUI packages: schematic canvas, waveform viewer, app shell.

An explicit (non-namespace) package, so that PyInstaller's static import
analysis reliably discovers ``gui.schematic`` and ``gui.waveform`` as
sub-packages to bundle -- without this file present, ``gui`` is an implicit
PEP 420 namespace package, which was found to make PyInstaller silently drop
``gui.waveform`` from the packaged ``.exe`` (see ``scripts/build_exe.py``).

This file intentionally contains no other code: sub-package ownership
(``gui/schematic/``, ``gui/waveform/``, ``gui/app.py``) is unchanged, see
``CLAUDE.md``.
"""
from __future__ import annotations
