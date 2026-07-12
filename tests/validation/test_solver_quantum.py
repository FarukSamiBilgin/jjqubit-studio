"""Comparison of solver-quantum output against the independent reference.

These tests SKIP (not fail) until solver-quantum lands, because its module path
and output format are not frozen yet. Once solver-quantum reports its API, wire
the ``_load_quantum_result`` helper below to its real entry point / HDF5 layout;
the assertions then compare its Ej, Ec, E01, anharmonicity and chi for
examples/transmon_readout.json against this suite's ground truth.

Expected ground truth (Cj+Cs+Cg = 77 fF convention), from reference.py:
    Ej/h  ~ 14.90 GHz   Ec/h ~ 251.6 MHz   Ej/Ec ~ 59
    E01   ~ 5.211 GHz   anharmonicity ~ -285 MHz
"""
from __future__ import annotations

import numpy as np
import pytest

from . import reference as ref


def _load_quantum_result():
    """Return a solver-quantum result for the example transmon, or skip.

    TODO(solver-quantum): replace this stub with the real call once the API is
    known, e.g. ``from core.solvers.quantum import solve; return solve(netlist)``
    or a reader for the emitted HDF5 file. Until then, skip cleanly.
    """
    pytest.importorskip(
        "core.solvers.quantum",
        reason="solver-quantum not implemented yet; comparison pending its API.",
    )
    pytest.skip(
        "solver-quantum module present but its output format is not wired into "
        "the validation harness yet -- ping validation with the result schema."
    )


def test_quantum_e01_matches_reference():
    """solver-quantum E01 must match the independent reference within 2%."""
    result = _load_quantum_result()
    r = ref.example_transmon_reference()
    assert np.isclose(result["e01_hz"], r.e01_hz, rtol=0.02)


def test_quantum_anharmonicity_matches_reference():
    """solver-quantum anharmonicity must match the reference within 5%."""
    result = _load_quantum_result()
    r = ref.example_transmon_reference()
    assert np.isclose(result["anharmonicity_hz"], r.anharmonicity_hz, rtol=0.05)


def test_quantum_ej_ec_match_reference():
    """solver-quantum Ej and Ec must match the reference (convention-dependent)."""
    result = _load_quantum_result()
    r = ref.example_transmon_reference()
    assert np.isclose(result["ej_hz"], r.ej_hz, rtol=0.02)
    # Ec is convention-dependent (72 vs 77 fF); accept either within 8%.
    ec_alt = ref.charging_energy_hz(ref.EXAMPLE_CJ_F + ref.EXAMPLE_CS_F)
    assert np.isclose(result["ec_hz"], r.ec_hz, rtol=0.08) or np.isclose(
        result["ec_hz"], ec_alt, rtol=0.08
    )
