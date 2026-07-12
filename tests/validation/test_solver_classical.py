"""Comparison of solver-classical (RCSJ) output against the independent reference.

These tests SKIP until solver-classical lands. The key acceptance check is the
analytic limit from CLAUDE.md: for I < Ic the DC voltage must be zero. Once
solver-classical exposes its API / HDF5 layout, wire ``_run_rcsj`` to it; the
subcritical case must return ~zero DC voltage and the supercritical case a
finite voltage matching reference.rcsj_dc_voltage_volt.
"""
from __future__ import annotations

import numpy as np
import pytest

from . import reference as ref

_IC_A = 20e-9
_RN_OHM = 8e3
_C_F = 53e-15
_V_SCALE = ref.PHI0 / 1e-9  # ~2.07 uV natural voltage scale


def _run_rcsj(bias_current_a: float):
    """Return solver-classical DC voltage (volts) for a biased junction, or skip.

    TODO(solver-classical): replace with the real entry point once known, e.g.
    ``from core.solvers.classical import rcsj_solve`` or an HDF5 reader for the
    time-domain trace (take the late-time average of V).
    """
    pytest.importorskip(
        "core.solvers.classical",
        reason="solver-classical not implemented yet; comparison pending its API.",
    )
    pytest.skip(
        "solver-classical module present but its output format is not wired into "
        "the validation harness yet -- ping validation with the result schema."
    )


def test_classical_subcritical_zero_voltage():
    """I < Ic: solver-classical DC voltage must be ~zero (the CLAUDE.md limit)."""
    v_dc = _run_rcsj(0.5 * _IC_A)
    assert abs(v_dc) < 1e-3 * _V_SCALE


def test_classical_supercritical_matches_reference():
    """I > Ic: solver-classical DC voltage must match the reference integrator."""
    i_bias = 2.0 * _IC_A
    v_dc = _run_rcsj(i_bias)
    v_ref = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, i_bias)
    assert np.isclose(v_dc, v_ref, rtol=0.05)
