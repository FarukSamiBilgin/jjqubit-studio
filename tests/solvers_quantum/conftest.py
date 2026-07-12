"""Pytest bootstrap and shared fixtures for the quantum-solver tests.

Ensures the repository root is importable so ``import core.solvers.quantum``
and ``import core.netlist`` work no matter where pytest is invoked from. This
lives inside ``tests/solvers_quantum/`` (this module's owned scope) and
touches nothing outside it.
"""
from __future__ import annotations

import pathlib
import sys

# tests/solvers_quantum/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from core.netlist import Netlist, load


@pytest.fixture
def examples_dir() -> pathlib.Path:
    """Path to the repo's shared ``examples/`` directory (owned by Task #1)."""
    return REPO_ROOT / "examples"


@pytest.fixture
def transmon_netlist(examples_dir: pathlib.Path) -> Netlist:
    """The bundled transmon + readout resonator reference circuit, validated."""
    return load(examples_dir / "transmon_readout.json", validate=True)


@pytest.fixture
def rcsj_netlist(examples_dir: pathlib.Path) -> Netlist:
    """The bundled RCSJ bias circuit: has a junction but NO resonator.

    Useful as a topology-error fixture (quantum solver should refuse it, not
    guess at a missing resonator).
    """
    return load(examples_dir / "rcsj_bias.json", validate=True)
