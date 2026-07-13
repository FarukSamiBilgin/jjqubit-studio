"""Pytest bootstrap for the scriptable-API tests.

Ensures the repository root is importable so ``import jjqubit`` and
``import core.netlist`` work no matter where pytest is invoked from. No Qt is
involved: the ``jjqubit`` API is deliberately GUI-free.
"""

from __future__ import annotations

import pathlib
import sys

# tests/api/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLES_DIR = REPO_ROOT / "examples"
