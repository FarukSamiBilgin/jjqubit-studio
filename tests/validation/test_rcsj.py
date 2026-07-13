"""Analytic-limit test #3: RCSJ zero-voltage branch for I < Ic.

CLAUDE.md requires: "the RCSJ solver must give zero DC voltage for I < Ic". Here
we validate the *physics itself* with an independent from-scratch RCSJ ODE
integrator (reference.rcsj_dc_voltage_volt), which then serves as the ground-
truth comparison target for solver-classical. Below the critical current the
gauge-invariant phase settles to phi = arcsin(I/Ic) with phi' -> 0, so the DC
(time-averaged) Josephson voltage V = (hbar/2e) <phi'> is zero. Above Ic the
phase runs and a finite DC voltage appears.

Grounding: from-scratch RCSJ ODE integration (Tinkham eq. 6.28).

NOTE for solver-classical: the shipped example examples/rcsj_bias.json is biased
ABOVE critical current (Ib = 25 nA > Ic = 20 nA), i.e. it is a *running-state*
example, not a zero-voltage one. The subcritical case below is constructed
explicitly.
"""

from __future__ import annotations

import numpy as np
import pytest

from . import reference as ref

# A representative junction (same scale as the example netlists).
_IC_A = 20e-9  # 20 nA critical current
_RN_OHM = 8e3  # 8 kohm
_C_F = 53e-15  # 53 fF (Cj + shunt)

# Voltage scale for tolerances: one flux quantum per nanosecond ~ 2 uV. The
# supercurrent branch should be many orders of magnitude below this.
_V_SCALE = ref.PHI0 / 1e-9  # ~2.07e-6 V


@pytest.mark.parametrize("frac", [0.0, 0.25, 0.5, 0.8, 0.95])
def test_subcritical_bias_gives_zero_dc_voltage(frac):
    """For I < Ic the DC voltage is zero (the supercurrent branch)."""
    i_bias = frac * _IC_A
    v_dc = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, i_bias)
    # Zero to numerical noise: << 1e-4 of the natural voltage scale.
    assert abs(v_dc) < 1e-4 * _V_SCALE


def test_supercritical_bias_gives_finite_dc_voltage():
    """For I clearly above Ic a finite positive DC voltage develops."""
    i_bias = 2.0 * _IC_A
    v_dc = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, i_bias)
    assert v_dc > 0.1 * _V_SCALE


def test_running_state_voltage_approaches_ohmic_branch():
    """Well above Ic, V -> R * sqrt(I^2 - Ic^2) (overdamped high-bias limit).

    At I >> Ic the sin term averages out and the junction looks resistive. For a
    strongly biased junction V approaches Rn*sqrt(I^2 - Ic^2). We check the DC
    voltage is within 20% of this analytic branch at I = 4 Ic.
    """
    i_bias = 4.0 * _IC_A
    v_dc = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, i_bias)
    v_ohmic = _RN_OHM * np.sqrt(i_bias**2 - _IC_A**2)
    assert np.isclose(v_dc, v_ohmic, rtol=0.20)


def test_zero_voltage_is_symmetric_in_bias_sign():
    """A negative subcritical bias likewise yields ~zero DC voltage."""
    v_pos = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, 0.5 * _IC_A)
    v_neg = ref.rcsj_dc_voltage_volt(_IC_A, _RN_OHM, _C_F, -0.5 * _IC_A)
    assert abs(v_pos) < 1e-4 * _V_SCALE
    assert abs(v_neg) < 1e-4 * _V_SCALE
