"""Pytest bootstrap for the app-shell GUI tests (Task #6).

Ensures the repository root is importable so ``import core.netlist`` and
``import gui.app`` work no matter where pytest is invoked from. Also forces
the Qt "offscreen" platform plugin so widget/window tests can run headless
(no display required), and provides a shared, session-scoped ``QApplication``
since Qt only allows one per process. Mirrors ``tests/schematic/conftest.py``.

Lives inside ``tests/app/`` (this module's owned scope) and touches nothing
outside it.
"""
from __future__ import annotations

import os
import pathlib
import sys

# tests/app/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLES_DIR = REPO_ROOT / "examples"

# Run Qt headlessly unless a real display/platform was explicitly requested.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402 - must follow sys.path setup


@pytest.fixture(scope="session")
def qapp():
    """A single shared ``QApplication`` for the whole test session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app
