"""Pytest bootstrap for the physics-validation suite.

Ensures the repository root is importable so ``import core.netlist`` works no
matter where pytest is invoked from, and exposes small helpers shared by the
validation tests. This file lives inside ``tests/validation/`` (this teammate's
owned scope) and touches nothing outside it.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

# tests/validation/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLES_DIR = REPO_ROOT / "examples"


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def examples_dir() -> pathlib.Path:
    """Absolute path to the ``examples/`` netlist directory."""
    return EXAMPLES_DIR
