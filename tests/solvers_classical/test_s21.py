"""Tests for core.solvers.classical.s21: readout notch resonance + line transmission."""
from __future__ import annotations

import numpy as np
import pytest

from core.solvers.classical.s21 import (
    compute_s21_curve,
    external_kappa_hz,
    line_transmission_factor,
    notch_response,
    resonator_lc_from_f0,
)

_F0_HZ = 7.2e9
_Z0_OHM = 50.0
_CK_F = 8e-15
_LENGTH_M = 6e-3
_EPS_EFF = 6.45
_Q_INTERNAL = 8000.0


class TestResonatorLcFromF0:
    def test_recovers_f0(self):
        l_h, c_f = resonator_lc_from_f0(_F0_HZ, _Z0_OHM)
        f0_recovered = 1.0 / (2.0 * np.pi * np.sqrt(l_h * c_f))
        assert f0_recovered == pytest.approx(_F0_HZ, rel=1e-9)

    def test_recovers_impedance(self):
        l_h, c_f = resonator_lc_from_f0(_F0_HZ, _Z0_OHM)
        z_recovered = np.sqrt(l_h / c_f)
        assert z_recovered == pytest.approx(_Z0_OHM, rel=1e-9)


class TestExternalKappa:
    def test_positive_and_grows_with_coupling_capacitance(self):
        _, c_r = resonator_lc_from_f0(_F0_HZ, _Z0_OHM)
        k_small = external_kappa_hz(_F0_HZ, 1e-15, c_r, _Z0_OHM)
        k_large = external_kappa_hz(_F0_HZ, 8e-15, c_r, _Z0_OHM)
        assert 0.0 < k_small < k_large

    def test_zero_coupling_gives_zero_kappa_ext(self):
        _, c_r = resonator_lc_from_f0(_F0_HZ, _Z0_OHM)
        assert external_kappa_hz(_F0_HZ, 0.0, c_r, _Z0_OHM) == 0.0


class TestNotchResponse:
    def test_far_detuned_response_is_near_unity(self):
        freq = np.array([_F0_HZ * 0.5])
        s21 = notch_response(freq, _F0_HZ, kappa_int_hz=1e6, kappa_ext_hz=1e6)
        assert abs(s21[0] - 1.0) < 1e-3

    def test_on_resonance_dip_depth_matches_formula(self):
        kappa_int_hz, kappa_ext_hz = 0.9e6, 2.36e6
        s21 = notch_response(np.array([_F0_HZ]), _F0_HZ, kappa_int_hz, kappa_ext_hz)
        expected = 1.0 - kappa_ext_hz / (kappa_int_hz + kappa_ext_hz)
        assert s21[0] == pytest.approx(expected, rel=1e-9)

    def test_symmetric_lorentzian_magnitude_around_f0(self):
        detuning = np.array([-1e6, 1e6]) + _F0_HZ
        s21 = notch_response(detuning, _F0_HZ, kappa_int_hz=1e6, kappa_ext_hz=1e6)
        assert abs(s21[0]) == pytest.approx(abs(s21[1]), rel=1e-9)


class TestLineTransmissionFactor:
    def test_matched_load_is_pure_unit_magnitude_delay(self):
        freq = np.linspace(6e9, 8e9, 11)
        factor = line_transmission_factor(freq, _Z0_OHM, _LENGTH_M, _EPS_EFF, termination_ohm=_Z0_OHM)
        assert np.allclose(np.abs(factor), 1.0, atol=1e-9)

    def test_mismatched_load_has_ripple(self):
        freq = np.linspace(6e9, 8e9, 401)
        factor = line_transmission_factor(freq, _Z0_OHM, _LENGTH_M, _EPS_EFF, termination_ohm=25.0)
        mag = np.abs(factor)
        assert mag.max() - mag.min() > 0.05  # standing-wave ripple from the mismatch

    def test_zero_length_matched_is_transparent(self):
        freq = np.array([_F0_HZ])
        factor = line_transmission_factor(freq, _Z0_OHM, 0.0, _EPS_EFF, termination_ohm=_Z0_OHM)
        assert factor[0] == pytest.approx(1.0 + 0.0j, abs=1e-9)


class TestComputeS21Curve:
    def test_bundled_example_parameters_give_a_notch_dip(self):
        curve = compute_s21_curve(
            f0_hz=_F0_HZ,
            q_internal=_Q_INTERNAL,
            coupling_capacitance_f=_CK_F,
            z0_ohm=_Z0_OHM,
            line_length_m=_LENGTH_M,
            eps_eff=_EPS_EFF,
            termination_ohm=_Z0_OHM,  # matched, as in examples/transmon_readout.json
        )
        mag = np.abs(curve.s21)
        idx_min = int(np.argmin(mag))
        # The dip sits at f0, and away from resonance the matched line is
        # (nearly) transparent.
        assert curve.frequency_hz[idx_min] == pytest.approx(_F0_HZ, rel=1e-3)
        assert mag[idx_min] < 0.9
        assert mag[0] > 0.95
        assert mag[-1] > 0.95

    def test_kappa_total_is_sum_of_internal_and_external(self):
        curve = compute_s21_curve(
            f0_hz=_F0_HZ,
            q_internal=_Q_INTERNAL,
            coupling_capacitance_f=_CK_F,
            z0_ohm=_Z0_OHM,
            line_length_m=_LENGTH_M,
            eps_eff=_EPS_EFF,
            termination_ohm=_Z0_OHM,
        )
        assert curve.kappa_total_hz == pytest.approx(curve.kappa_int_hz + curve.kappa_ext_hz)
        assert curve.kappa_int_hz == pytest.approx(_F0_HZ / _Q_INTERNAL)
