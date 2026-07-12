"""Pytest bootstrap and shared fixtures for the classical-solver tests.

Ensures the repository root is importable so ``import core.solvers.classical``
and ``import core.netlist`` work no matter where pytest is invoked from. This
lives inside ``tests/solvers_classical/`` (this module's owned scope) and
touches nothing outside it.
"""
from __future__ import annotations

import pathlib
import sys

# tests/solvers_classical/conftest.py -> parents[2] is the repository root.
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
def rcsj_netlist(examples_dir: pathlib.Path) -> Netlist:
    """The bundled current-biased RCSJ circuit (junction + current_source)."""
    return load(examples_dir / "rcsj_bias.json", validate=True)


@pytest.fixture
def transmon_netlist(examples_dir: pathlib.Path) -> Netlist:
    """The bundled transmon + readout resonator reference circuit, validated.

    Has a resonator/feedline/termination (readout topology) but NO
    current_source: useful as an RCSJ-topology-error fixture.
    """
    return load(examples_dir / "transmon_readout.json", validate=True)
