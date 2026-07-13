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

    chi_2level = 2 * g ^ 2 * omega_q / (omega_q ^ 2 - omega_r ^ 2)

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

import numpy as np
import pytest
import scqubits as scq
from core.solvers.quantum.dispersive import (
    DEFAULT_RESONATOR_IMPEDANCE_OHM,
    DISPERSIVE_VALIDITY_THRESHOLD,
    DispersiveRegimeWarning,
    compute_dispersive_shift,
    dressed_chi_ghz,
)
from core.solvers.quantum.quantization import quantize_circuit
from core.solvers.quantum.spectrum import compute_transmon_spectrum
from quantum_helpers import make_transmon_resonator_netlist


def _two_level_analytic_chi(
    g_eff_ghz: float, omega_q_ghz: float, omega_r_ghz: float
) -> float:
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
            transmon = scq.Transmon(
                EJ=Ej, EC=Ec, ng=0.0, ncut=40, truncated_dim=truncated_dim
            )
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
        assert dressed_chi_ghz(transmon, oscillator, 0.0) == pytest.approx(
            0.0, abs=1e-12
        )


class TestIndependentQuTiPCrossCheck:
    """Cross-check scqubits.HilbertSpace's chi against a from-scratch QuTiP
    diagonalization of the SAME physical multi-level model (same transmon
    eigenenergies and charge-matrix elements from scqubits, but composed and
    diagonalized entirely with QuTiP's own tensor/eigenstates machinery,
    independent of scqubits' HilbertSpace/add_interaction/generate_lookup
    code path). Both mandated libraries (CLAUDE.md's tech stack) agreeing to
    numerical precision on the full multi-level reference example is strong
    evidence the production dispersive.py pipeline has no library-specific
    bug -- this is not just self-consistency, it is agreement between two
    independent implementations of the same physics.
    """

    def test_qutip_diagonalization_matches_scqubits_hilbertspace(
        self, transmon_netlist
    ):
        import qutip as qt

        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)

        n_levels = len(spectrum.energy_levels_GHz)
        n_osc = 6
        levels = spectrum.energy_levels_GHz
        n_matrix = spectrum.transmon.n_operator(energy_esys=True)[:n_levels, :n_levels]
        g_bare = (
            result.g_GHz / spectrum.n01
        )  # same bare coefficient dispersive.py feeds internally

        h_qubit = qt.tensor(qt.Qobj(np.diag(levels)), qt.qeye(n_osc))
        a = qt.tensor(qt.qeye(n_levels), qt.destroy(n_osc))
        n_full = qt.tensor(qt.Qobj(n_matrix), qt.qeye(n_osc))
        hamiltonian = (
            h_qubit + result.f0_GHz * a.dag() * a + g_bare * n_full * (a + a.dag())
        )

        evals_full, evecs_full = hamiltonian.eigenstates()

        def dressed_energy(qubit_level: int, photon_number: int) -> tuple[float, float]:
            bare = qt.tensor(
                qt.basis(n_levels, qubit_level), qt.basis(n_osc, photon_number)
            )
            overlaps = [abs(bare.overlap(v)) ** 2 for v in evecs_full]
            idx = int(np.argmax(overlaps))
            return evals_full[idx], overlaps[idx]

        e00, o00 = dressed_energy(0, 0)
        e01, o01 = dressed_energy(0, 1)
        e10, o10 = dressed_energy(1, 0)
        e11, o11 = dressed_energy(1, 1)
        # Every dressed state should be clearly, unambiguously identifiable
        # with its bare product state (deep dispersive regime).
        assert min(o00, o01, o10, o11) > 0.99

        chi_qutip = ((e11 - e10) - (e01 - e00)) / 2.0
        assert result.chi_GHz == pytest.approx(chi_qutip, rel=1e-6)


class TestGDoesNotDoubleCountChargeMatrixElement:
    """Regression test for a real bug caught in review (see team log): g_GHz
    must be the COMPLETE physical g_01 = 2*e*beta*n01*delta_V0/h, and the
    value fed internally to dressed_chi_ghz (which multiplies the FULL n
    operator, itself carrying a factor of n01 for the 0<->1 transition) must
    be g_01/n01 -- NOT g_01 itself, which would double-count n01 and inflate
    the effective simulated coupling (and therefore chi) by a factor of n01
    relative to the intended physical model.
    """

    def test_reported_g_matches_independent_krantz_formula(self, transmon_netlist):
        import math

        from scipy.constants import e as ELEMENTARY_CHARGE
        from scipy.constants import h as PLANCK_H
        from scipy.constants import hbar as HBAR

        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)

        beta = quantization.Cg_fF / quantization.C_sigma_fF
        omega_r = 2.0 * math.pi * result.f0_GHz * 1e9
        delta_v0 = omega_r * math.sqrt(HBAR * DEFAULT_RESONATOR_IMPEDANCE_OHM / math.pi)
        g_01_reference = (
            2.0 * ELEMENTARY_CHARGE * beta * spectrum.n01 * delta_v0 / PLANCK_H / 1e9
        )
        assert result.g_GHz == pytest.approx(g_01_reference, rel=1e-9)

    def test_chi_matches_manual_diagonalization_with_bare_coefficient(
        self, transmon_netlist
    ):
        # Independently reproduce compute_dispersive_shift's chi by manually
        # dividing out n01 before calling dressed_chi_ghz, and confirm it
        # matches -- pinning down that the production code does the same.
        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)

        g_bare = result.g_GHz / spectrum.n01
        oscillator = scq.Oscillator(E_osc=result.f0_GHz, truncated_dim=6)
        chi_manual = dressed_chi_ghz(spectrum.transmon, oscillator, g_bare)
        assert result.chi_GHz == pytest.approx(chi_manual, rel=1e-9)

    def test_using_g_as_bare_coefficient_would_have_inflated_chi(
        self, transmon_netlist
    ):
        # Demonstrates the bug this guards against: feeding g_GHz (physical,
        # already includes n01) directly as the bare coefficient inflates
        # the effective coupling and gives a measurably different (larger
        # magnitude) chi than the correct calculation.
        quantization = quantize_circuit(transmon_netlist)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)

        oscillator = scq.Oscillator(E_osc=result.f0_GHz, truncated_dim=6)
        chi_if_buggy = dressed_chi_ghz(spectrum.transmon, oscillator, result.g_GHz)
        assert abs(chi_if_buggy) > abs(result.chi_GHz)
        assert chi_if_buggy != pytest.approx(result.chi_GHz, rel=1e-6)


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
        result_50 = compute_dispersive_shift(
            quantization, spectrum, resonator_impedance_ohm=50.0
        )
        result_200 = compute_dispersive_shift(
            quantization, spectrum, resonator_impedance_ohm=200.0
        )
        # delta_V0 ~ sqrt(Z_r), so g ~ sqrt(Z_r): quadrupling Z_r should
        # double g (documents the sensitivity of g to the approved-but-
        # assumed resonator impedance, see dispersive.py module docstring).
        assert result_200.g_GHz / result_50.g_GHz == pytest.approx(
            math.sqrt(4.0), rel=1e-6
        )


class TestDispersiveRegimeGuard:
    """The solver must flag (and warn) when |g/Delta| leaves the dispersive regime."""

    def test_far_detuned_is_valid_and_silent(self, recwarn):
        # Default helper: transmon ~5 GHz, resonator 7.2 GHz -> far detuned.
        net = make_transmon_resonator_netlist(f0_GHz=7.2)
        quantization = quantize_circuit(net)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)
        assert result.dispersive_regime_valid is True
        assert result.g_over_Delta < DISPERSIVE_VALIDITY_THRESHOLD
        assert not any(
            issubclass(w.category, DispersiveRegimeWarning) for w in recwarn.list
        )

    def test_on_resonance_is_invalid_and_warns(self):
        # Tune the resonator ONTO the qubit's E01 so Delta -> 0.
        net = make_transmon_resonator_netlist(f0_GHz=7.2)
        quantization = quantize_circuit(net)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        on_res = make_transmon_resonator_netlist(f0_GHz=spectrum.E01_GHz)
        q2 = quantize_circuit(on_res)
        s2 = compute_transmon_spectrum(q2.Ej_GHz, q2.Ec_GHz)
        with pytest.warns(DispersiveRegimeWarning):
            result = compute_dispersive_shift(q2, s2)
        assert result.dispersive_regime_valid is False
        assert result.g_over_Delta >= DISPERSIVE_VALIDITY_THRESHOLD

    def test_g_over_delta_matches_abs_g_over_delta(self):
        net = make_transmon_resonator_netlist(f0_GHz=7.2)
        quantization = quantize_circuit(net)
        spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
        result = compute_dispersive_shift(quantization, spectrum)
        assert result.g_over_Delta == pytest.approx(
            abs(result.g_GHz / result.Delta_GHz), rel=1e-12
        )
