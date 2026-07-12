"""Tests for the dispersive shift chi (core.solvers.quantum.dispersive).

The key CLAUDE.md-mandated check here is: "Dispersif kayma chi, bilinen
analitik ifadeye yakinsamali" (chi must converge to the known analytic
expression in the dispersive limit, g << Delta).

Ground-truth closed form used below
------------------------------------
For a strictly 2-level qubit capacitively coupled to a resonator via the
FULL (non rotating-wave-approximated) interaction H_int = g*sigma_x*(a+a-dag)
-- i.e. exactly what :func:`core.solvers.quantum.dispersive.dressed_chi_ghz`
diagonalizes when the transmon is truncated to 2 levels -- 2nd-order
non-degenerate perturbation theory gives the EXACT dispersive shift::

    chi_2level = 2 * g^2 * omega_q / (omega_q^2 - omega_r^2)

(derived independently in this docstring's accompanying investigation, not
taken from a half-remembered literature formula; it reduces to the textbook
chi = g^2/Delta, Delta = omega_q - omega_r, in the near-resonant limit
omega_q ~= omega_r, and was cross-checked against an independent QuTiP
Jaynes-Cummings + Bloch-Siegert diagonalization). This is the "known
analytic limit" this module's chi computation is validated against.

The full multi-level transmon (truncated_dim > 2) is NOT expected to match
this 2-level formula quantitatively -- higher transmon levels (weak
anharmonicity) genuinely shift chi, a real, well-documented effect (Koch et
al., PRA 76, 042319 (2007)) -- so those tests instead check numerical
convergence with truncation and correct g^2 scaling in the dispersive limit.
"""
from __future__ import annotations

import math

import pytest
import scqubits as scq

from core.solvers.quantum.dispersive import (
    DEFAULT_RESONATOR_IMPEDANCE_OHM,
    compute_dispersive_shift,
    dressed_chi_ghz,
)
from core.solvers.quantum.quantization import quantize_circuit
from core.solvers.quantum.spectrum import compute_transmon_spectrum
from helpers import make_transmon_resonator_netlist


def _two_level_analytic_chi(g_eff_ghz: float, omega_q_ghz: float, omega_r_ghz: float) -> float:
    """The exact 2-level (non-RWA) dispersive shift; see module docstring."""
    return 2.0 * g_eff_ghz**2 * omega_q_ghz / (omega_q_ghz**2 - omega_r_ghz**2)


class TestTwoLevelAnalyticLimit:
    """dressed_chi_ghz, at truncated_dim=2, must reproduce the exact formula."""

    @pytest.mark.parametrize(
        "Ej,Ec,f0,g_input",
        [
            (14.9, 0.2515, 7.2, 0.002),
            (14.9, 0.2515, 7.2, 0.02),
            (20.0, 0.3, 6.0, 0.01),
            (30.0, 0.25, 8.5, 0.01),
        ],
    )
    def test_matches_closed_form_at_truncated_dim_2(self, Ej, Ec, f0, g_input):
        transmon = scq.Transmon(EJ=Ej, EC=Ec, ng=0.0, ncut=40, truncated_dim=2)
        oscillator = scq.Oscillator(E_osc=f0, truncated_dim=6)
        n01 = abs(transmon.n_operator(energy_esys=True)[0, 1])
        g_eff = g_input * n01
        omega_q = transmon.E01()

        chi_numeric = dressed_chi_ghz(transmon, oscillator, g_input)
        chi_analytic = _two_level_analytic_chi(g_eff, omega_q, f0)

        assert chi_numeric == pytest.approx(chi_analytic, rel=1e-3)

    def test_reduces_to_textbook_g_squared_over_delta_near_resonance(self):
        # omega_q close to omega_r: 2*wq/(wq^2-wr^2) ~= 1/(wq-wr) = 1/Delta.
        transmon = scq.Transmon(EJ=14.9, EC=0.2515, ng=0.0, ncut=40, truncated_dim=2)
        oscillator = scq.Oscillator(E_osc=5.20, truncated_dim=6)  # close to E01~5.21
        n01 = abs(transmon.n_operator(energy_esys=True)[0, 1])
        # Delta here is deliberately tiny (~10 MHz) to test the near-resonant
        # limit, so g must be kept much smaller still to stay in the g<<Delta
        # perturbative regime this textbook formula assumes.
        g_input = 0.0001
        g_eff = g_input * n01
        omega_q = transmon.E01()
        delta = omega_q - 5.20

        chi_numeric = dressed_chi_ghz(transmon, oscillator, g_input)
        chi_textbook = g_eff**2 / delta
        assert chi_numeric == pytest.approx(chi_textbook, rel=0.02)


class TestMultilevelConvergenceAndScaling:
    def test_chi_converges_as_truncation_dimension_increases(self):
        Ej, Ec, f0, g_input = 14.9, 0.2515, 7.2, 0.02
        chis = []
        for truncated_dim in [4, 6, 8, 10]:
            transmon = scq.Transmon(EJ=Ej, EC=Ec, ng=0.0, ncut=40, truncated_dim=truncated_dim)
            oscillator = scq.Oscillator(E_osc=f0, truncated_dim=6)
            chis.append(dressed_chi_ghz(transmon, oscillator, g_input))
        # Truncation dimensions 6, 8, 10 should agree tightly (numerically
        # converged); only the very small dim=4 truncation may lag behind.
        assert chis[1] == pytest.approx(chis[2], rel=1e-3)
        assert chis[2] == pytest.approx(chis[3], rel=1e-3)

    def test_chi_scales_as_g_squared_in_dispersive_limit(self):
        Ej, Ec, f0 = 14.9, 0.2515, 7.2
        transmon = scq.Transmon(EJ=Ej, EC=Ec, ng=0.0, ncut=40, truncated_dim=6)
        oscillator = scq.Oscillator(E_osc=f0, truncated_dim=6)
        g_values = [0.002, 0.004, 0.02]
        ratios = [dressed_chi_ghz(transmon, oscillator, g) / g**2 for g in g_values]
        # chi/g^2 should be essentially constant (dispersive/perturbative regime).
        assert ratios[0] == pytest.approx(ratios[1], rel=1e-2)
        assert ratios[1] == pytest.approx(ratios[2], rel=1e-2)

    def test_zero_coupling_gives_zero_chi(self):
        transmon = scq.Transmon(EJ=14.9, EC=0.2515, ng=0.0, ncut=40, truncated_dim=6)
        oscillator = scq.Oscillator(E_osc=7.2, truncated_dim=6)
        assert dressed_chi_ghz(transmon, oscillator, 0.0) == pytest.approx(0.0, abs=1e-12)


class TestComputeDispersiveShiftEndToEnd:
    def test_reference_example_is_physically_sane(self, transmon_netlist):
        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)

        # g should be in the typical experimental range (tens to a few
        # hundred MHz), not zero and not GHz-scale (which would violate the
        # weak-coupling assumption baked into the dispersive-regime formulas).
        assert 0.01 < result.g_GHz < 0.3
        # Firmly in the dispersive regime: g << |Delta|.
        assert abs(result.g_GHz) < 0.1 * abs(result.Delta_GHz)
        # chi should be small and of the sign/magnitude expected in the
        # dispersive regime: |chi| << |g|.
        assert 0.0 < abs(result.chi_GHz) < 0.1 * result.g_GHz
        assert result.resonator_Z0_ohm == DEFAULT_RESONATOR_IMPEDANCE_OHM
        assert result.kappa_GHz == pytest.approx(7.2 / 8000.0, rel=1e-9)

    def test_no_coupling_capacitor_gives_zero_g_and_chi(self):
        nl = make_transmon_resonator_netlist()
        nl.elements = [el for el in nl.elements if el.id != "Cg"]
        nl.connections = [c for c in nl.connections if c.element != "Cg"]
        quantization = quantize_circuit(nl)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)
        assert result.g_GHz == 0.0
        assert result.chi_GHz == 0.0

    def test_g_scales_with_sqrt_of_assumed_resonator_impedance(self, transmon_netlist):
        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result_50 = compute_dispersive_shift(quantization, spectrum, resonator_impedance_ohm=50.0)
        result_200 = compute_dispersive_shift(
            quantization, spectrum, resonator_impedance_ohm=200.0
        )
        # delta_V0 ~ sqrt(Z_r), so g ~ sqrt(Z_r): quadrupling Z_r should
        # double g (documents the sensitivity of g to the approved-but-
        # assumed resonator impedance, see dispersive.py module docstring).
        assert result_200.g_GHz / result_50.g_GHz == pytest.approx(math.sqrt(4.0), rel=1e-6)
