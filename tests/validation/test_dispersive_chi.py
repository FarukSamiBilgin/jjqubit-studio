"""Analytic-limit test #4: dispersive shift chi converges to the analytic value.

CLAUDE.md requires: "the dispersive shift chi should converge to the known
analytic expression". The trap here is *which* analytic expression:

* The popular compact formula chi = g^2 * alpha / (Delta*(Delta+alpha)) assumes
  ideal harmonic-ladder matrix elements |n_12|/|n_01| = sqrt(2). For a realistic
  transmon |n_12|/|n_01| ~ 1.37, and this formula is ~30% off.
* The correct target is the full multilevel second-order sum with the *real*
  transmon charge matrix elements.

We validate by comparing the multilevel reference formula against a direct
QuTiP diagonalization of the coupled transmon+resonator, which requires no
perturbative approximation. In the dispersive limit (small g) they must agree to
~1%, and chi must scale as g^2. We also assert the compact formula is
*measurably* different, documenting why the solver must not use it.

Grounding: from-scratch charge-basis transmon + direct QuTiP diagonalization.
"""

from __future__ import annotations

import numpy as np
import pytest

from . import reference as ref

# Reference transmon energies (Hz) and geometry for these tests.
_EJ_HZ = ref.josephson_energy_hz(ref.EXAMPLE_IC_A)
_EC_HZ = ref.charging_energy_hz(ref.EXAMPLE_C_SIGMA_F)
_WR_HZ = ref.EXAMPLE_RESONATOR_HZ


def _transmon_levels_and_n(nlevels: int, ncut: int = 50):
    """Return (levels_hz shifted so ground=0, n_matrix) for the reference transmon."""
    evals, evecs = ref.cpb_eigensystem_hz(_EJ_HZ, _EC_HZ, ng=0.0, ncut=ncut)
    levels = evals[:nlevels] - evals[0]
    n_matrix = ref.number_operator_matrix(evecs, ncut, nlevels)
    return levels, n_matrix


def _chi_numeric_qutip(g_hz: float, nlevels: int = 6, n_fock: int = 25) -> float:
    """Dispersive shift chi (Hz) from a direct QuTiP diagonalization.

    Builds H = H_transmon (x) I + I (x) H_resonator + (g/n01) n (x) (a + a^dag),
    diagonalizes exactly, and reads chi = [(E_11 - E_10) - (E_01 - E_00)] / 2 by
    identifying dressed states via maximum overlap with the bare product states.
    """
    qt = pytest.importorskip("qutip")
    levels, n_matrix = _transmon_levels_and_n(nlevels)
    n01 = abs(n_matrix[0, 1])

    h_q = qt.Qobj(np.diag(levels))
    a = qt.destroy(n_fock)
    h_r = _WR_HZ * a.dag() * a
    nmat = qt.Qobj(np.array(n_matrix))
    coupling = (g_hz / n01) * qt.tensor(nmat, a + a.dag())
    h = qt.tensor(h_q, qt.qeye(n_fock)) + qt.tensor(qt.qeye(nlevels), h_r) + coupling

    evals, estates = h.eigenstates()

    def dressed_energy(q_state: int, r_state: int) -> float:
        bare = qt.tensor(qt.basis(nlevels, q_state), qt.basis(n_fock, r_state))
        overlaps = [abs(bare.overlap(v)) ** 2 for v in estates]
        return evals[int(np.argmax(overlaps))]

    e00 = dressed_energy(0, 0)
    e10 = dressed_energy(1, 0)
    e01 = dressed_energy(0, 1)
    e11 = dressed_energy(1, 1)
    return ((e11 - e10) - (e01 - e00)) / 2.0


def test_multilevel_formula_matches_direct_diagonalization():
    """Multilevel chi formula agrees with exact diagonalization to <1.5% (small g)."""
    g_hz = 50e6  # 50 MHz coupling: dispersive (g/Delta ~ 0.025)
    levels, n_matrix = _transmon_levels_and_n(6)
    chi_formula = ref.dispersive_shift_multilevel_hz(levels, n_matrix, g_hz, _WR_HZ)
    chi_numeric = _chi_numeric_qutip(g_hz)
    assert np.isclose(chi_formula, chi_numeric, rtol=0.015)


def test_chi_scales_quadratically_with_coupling():
    """chi ~ g^2 in the dispersive regime: doubling g quadruples chi."""
    levels, n_matrix = _transmon_levels_and_n(6)
    chi_g = ref.dispersive_shift_multilevel_hz(levels, n_matrix, 20e6, _WR_HZ)
    chi_2g = ref.dispersive_shift_multilevel_hz(levels, n_matrix, 40e6, _WR_HZ)
    assert np.isclose(chi_2g / chi_g, 4.0, rtol=1e-6)


def test_chi_sign_matches_detuning():
    """For a qubit below the resonator (Delta < 0) the reference chi is negative."""
    levels, n_matrix = _transmon_levels_and_n(6)
    delta = levels[1] - _WR_HZ
    assert delta < 0.0
    chi = ref.dispersive_shift_multilevel_hz(levels, n_matrix, 50e6, _WR_HZ)
    assert chi < 0.0


def test_simple_formula_is_a_poor_target():
    """Document that the compact 2-level+alpha formula deviates ~30% here.

    This is a guardrail: if a solver reports chi matching the simple formula
    (not the multilevel one), it is using the wrong expression for this transmon.
    """
    g_hz = 50e6
    levels, n_matrix = _transmon_levels_and_n(6)
    r = ref.transmon_reference(_EJ_HZ, _EC_HZ)
    chi_full = ref.dispersive_shift_multilevel_hz(levels, n_matrix, g_hz, _WR_HZ)
    chi_simple = ref.dispersive_shift_simple_hz(
        r.e01_hz, r.anharmonicity_hz, g_hz, _WR_HZ
    )
    rel_gap = abs(chi_simple / chi_full - 1.0)
    assert rel_gap > 0.2  # the two differ by well over 20%
