"""Tests for core.solvers.classical.rcsj: the RCSJ phase ODE, I-V sweep.

The central analytic-limit check CLAUDE.md requires ("RCSJ solver must give
zero DC voltage for I < Ic") is validated here directly against this
module's own physics. The independent-reference cross-check
(``tests/validation/reference.rcsj_dc_voltage_volt``) is VALIDATION's own
scope/test (``tests/validation/test_solver_classical.py``) -- it runs against
this solver's public API/CLI output rather than this module reaching into
``tests/validation/`` itself, per project file ownership (CLAUDE.md).
"""

from __future__ import annotations

import numpy as np
import pytest
from core.solvers.classical.rcsj import (
    dc_voltage,
    integrate_phase_dynamics,
    plasma_frequency_rad_s,
    sweep_iv_curve,
)

# A representative junction (same scale as tests/validation/test_rcsj.py's
# fixture, itself matching examples/rcsj_bias.json's Ic/Rn and Cj+Cs total).
_IC_A = 20e-9
_R_OHM = 8e3
_C_F = 53e-15
_PHI0 = 2.0678338e-15  # h / 2e, Wb (for an independent voltage scale below)
_V_SCALE = _PHI0 / 1e-9  # ~2.07 uV: one flux quantum per ns


class TestZeroVoltageLimit:
    """The CLAUDE.md physics-validation-rule limit: I < Ic => V_dc = 0."""

    @pytest.mark.parametrize("frac", [0.0, 0.25, 0.5, 0.8, 0.95])
    def test_subcritical_bias_gives_zero_dc_voltage(self, frac):
        v_dc = dc_voltage(_IC_A, _R_OHM, _C_F, frac * _IC_A)
        assert abs(v_dc) < 1e-4 * _V_SCALE

    def test_negative_subcritical_bias_is_symmetric(self):
        v_pos = dc_voltage(_IC_A, _R_OHM, _C_F, 0.5 * _IC_A)
        v_neg = dc_voltage(_IC_A, _R_OHM, _C_F, -0.5 * _IC_A)
        assert abs(v_pos) < 1e-4 * _V_SCALE
        assert abs(v_neg) < 1e-4 * _V_SCALE

    def test_supercritical_bias_gives_finite_dc_voltage(self):
        v_dc = dc_voltage(_IC_A, _R_OHM, _C_F, 2.0 * _IC_A)
        assert v_dc > 0.1 * _V_SCALE

    def test_running_state_approaches_ohmic_branch(self):
        # At I >> Ic the sin(phi) term averages out: V -> R*sqrt(I^2-Ic^2).
        i_bias = 4.0 * _IC_A
        v_dc = dc_voltage(_IC_A, _R_OHM, _C_F, i_bias)
        v_ohmic = _R_OHM * np.sqrt(i_bias**2 - _IC_A**2)
        assert np.isclose(v_dc, v_ohmic, rtol=0.20)


class TestPhaseDynamics:
    def test_zero_voltage_branch_phase_is_static(self):
        result = integrate_phase_dynamics(_IC_A, _R_OHM, _C_F, 0.5 * _IC_A)
        # On the supercurrent branch the phase should stay essentially at
        # its fixed point (no long-term drift).
        assert np.ptp(result.phase_rad) < 1e-3

    def test_running_state_phase_advances_monotonically_on_average(self):
        result = integrate_phase_dynamics(_IC_A, _R_OHM, _C_F, 2.0 * _IC_A)
        # A running junction's phase should have net secular growth.
        assert result.phase_rad[-1] > result.phase_rad[0] + 2.0 * np.pi

    def test_voltage_consistent_with_phase_derivative(self):
        # Internal self-consistency: the reported voltage_v must equal
        # PHI0_OVER_2PI * dphi/dt of the reported phase_rad trace. Checked
        # via a central-difference re-derivation of dphi/dt from the phase
        # array alone (independent of how voltage_v itself was computed
        # internally).
        #
        # The first/last sample are excluded: np.gradient falls back to a
        # one-sided (forward/backward) difference at the two trace
        # boundaries, which is a known lower-order approximation there --
        # e.g. at t=0 the true dphi/dt is exactly 0 (rest initial
        # condition) but the one-sided estimate from the first two points
        # is not, purely a finite-differencing artifact, not a solver
        # inconsistency (confirmed: excluding the endpoints drops the max
        # relative error from ~100% at the single edge point to <1%
        # throughout the interior).
        from core.solvers.classical.rcsj import PHI0_OVER_2PI

        result = integrate_phase_dynamics(_IC_A, _R_OHM, _C_F, 2.0 * _IC_A)
        dphi_dt = np.gradient(result.phase_rad, result.time_s)
        voltage_from_phase = PHI0_OVER_2PI * dphi_dt
        assert np.allclose(
            result.voltage_v[1:-1], voltage_from_phase[1:-1], rtol=0.02, atol=1e-9
        )


class TestPlasmaFrequency:
    def test_positive_and_scales_with_critical_current(self):
        wp_low = plasma_frequency_rad_s(10e-9, _C_F)
        wp_high = plasma_frequency_rad_s(40e-9, _C_F)
        assert wp_low > 0.0
        assert wp_high > wp_low  # omega_p ~ sqrt(Ic)


class TestIVSweepHysteresis:
    def test_ascending_sweep_is_zero_below_switching_and_finite_above(self):
        currents = np.linspace(0.0, 2.0 * _IC_A, 15)
        result = sweep_iv_curve(_IC_A, _R_OHM, _C_F, currents)
        below_ic = currents < 0.8 * _IC_A
        above_ic = currents > 1.2 * _IC_A
        assert np.all(np.abs(result.voltage_up_v[below_ic]) < 1e-3 * _V_SCALE)
        assert np.all(result.voltage_up_v[above_ic] > 0.05 * _V_SCALE)

    def test_underdamped_junction_shows_retrapping_hysteresis(self):
        # examples/rcsj_bias.json's junction is underdamped (Q ~ 14): the
        # descending sweep should still show finite voltage at currents
        # where the ascending sweep was already zero (a hysteresis loop).
        # i_mid = 0.5*Ic is comfortably below both Ic (switching current)
        # and comfortably ABOVE the retrapping current (~0.089*Ic per
        # validation's independent reference), so the ascending branch must
        # read zero there while the descending branch -- not yet retrapped
        # -- must still read finite.
        currents = np.linspace(0.0, 2.0 * _IC_A, 21)
        result = sweep_iv_curve(_IC_A, _R_OHM, _C_F, currents)
        i_mid = 0.5 * _IC_A
        v_up_at_mid = np.interp(i_mid, result.bias_current_up_a, result.voltage_up_v)
        v_down_at_mid = np.interp(
            i_mid, result.bias_current_down_a[::-1], result.voltage_down_v[::-1]
        )
        assert abs(v_up_at_mid) < 1e-3 * _V_SCALE
        assert (
            v_down_at_mid > 10.0 * abs(v_up_at_mid) or v_down_at_mid > 0.01 * _V_SCALE
        )

    def test_sweep_returns_up_and_down_of_equal_length(self):
        currents = np.linspace(0.0, 2.0 * _IC_A, 9)
        result = sweep_iv_curve(_IC_A, _R_OHM, _C_F, currents)
        assert len(result.bias_current_up_a) == len(currents)
        assert len(result.bias_current_down_a) == len(currents)
        assert result.bias_current_down_a[0] == pytest.approx(currents[-1])
        assert result.bias_current_down_a[-1] == pytest.approx(currents[0])
