"""Interoperability importers for externally-computed circuit data.

This package provides GUI-free, dependency-light readers for data produced by
external tools:

* :func:`read_capacitance_csv` -- a Maxwell capacitance matrix (fF) from CSV.
* :func:`read_touchstone_s2p` -- 2-port S-parameters from a Touchstone ``.s2p``.

These are pure file-I/O + validation layers. No physics is derived here; the
capacitance-to-Hamiltonian mapping lives in ``core/solvers/quantum``.
"""

from __future__ import annotations

from core.interop.capacitance_csv import (
    CapacitanceMatrix,
    read_capacitance_csv,
)
from core.interop.touchstone import Touchstone2Port, read_touchstone_s2p

__all__ = [
    "CapacitanceMatrix",
    "read_capacitance_csv",
    "Touchstone2Port",
    "read_touchstone_s2p",
]
