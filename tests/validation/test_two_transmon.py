"""Physics validation for the two-coupled-transmon spectrum (Faz 2).

The hallmark of qubit-qubit coupling is an avoided crossing in the
single-excitation manifold as the two qubits tune through resonance. These
checks pin that behavior against its analytic form
``splitting = 2*sqrt((Delta/2)^2 + J^2)``:

- On resonance the splitting is minimal and equals exactly 2J.
- J is linear in the coupling coefficient g.
- With g = 0 the two qubits are independent: the splitting is just the bare
  detuning and J = 0.
- The resonant splitting is smaller than the detuned splitting (the avoided
  crossing repels).
"""

from __future__ import annotations

import pytest
from core.solvers.quantum.multiqubit import compute_two_transmon_spectrum

EC = 0.25


class TestAvoidedCrossing:
    def test_on_resonance_splitting_is_twice_J(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        assert r.detuning_GHz == pytest.approx(0.0, abs=1e-9)
        assert r.one_excitation_splitting_GHz == pytest.approx(2.0 * r.J_GHz, rel=1e-6)
        assert r.J_GHz > 0.0

    def test_resonant_splitting_is_smaller_than_detuned(self):
        resonant = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        detuned = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.02)
        assert (
            resonant.one_excitation_splitting_GHz < detuned.one_excitation_splitting_GHz
        )


class TestExchangeCouplingScaling:
    def test_J_is_linear_in_g(self):
        j1 = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02).J_GHz
        j2 = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.04).J_GHz
        assert j2 == pytest.approx(2.0 * j1, rel=1e-3)

    def test_stronger_coupling_widens_the_resonant_gap(self):
        weak = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.01)
        strong = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.03)
        assert strong.J_GHz > weak.J_GHz


class TestDecoupledLimit:
    def test_zero_coupling_gives_zero_J_and_bare_detuning(self):
        r = compute_two_transmon_spectrum(15.0, EC, 13.0, EC, g_GHz=0.0)
        assert r.J_GHz == pytest.approx(0.0, abs=1e-6)
        # With no coupling the two single-excitation levels are just the bare
        # qubit frequencies, so their gap is the bare detuning.
        assert r.one_excitation_splitting_GHz == pytest.approx(
            abs(r.detuning_GHz), rel=1e-4
        )

    def test_off_resonance_splitting_follows_the_analytic_hyperbola(self):
        # splitting = 2 sqrt((Delta/2)^2 + J^2); check J extracted at resonance
        # predicts the detuned splitting from the same g.
        j = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02).J_GHz
        detuned = compute_two_transmon_spectrum(15.0, EC, 14.0, EC, g_GHz=0.02)
        delta = detuned.detuning_GHz
        predicted = 2.0 * ((delta / 2.0) ** 2 + j**2) ** 0.5
        assert detuned.one_excitation_splitting_GHz == pytest.approx(
            predicted, rel=0.05
        )


class TestApiContract:
    def test_rejects_nonpositive_energies(self):
        with pytest.raises(ValueError):
            compute_two_transmon_spectrum(0.0, EC, 15.0, EC, g_GHz=0.02)

    def test_rejects_too_few_evals(self):
        with pytest.raises(ValueError):
            compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02, evals_count=2)

    def test_ground_level_is_zero(self):
        r = compute_two_transmon_spectrum(15.0, EC, 15.0, EC, g_GHz=0.02)
        assert r.coupled_levels_GHz[0] == pytest.approx(0.0, abs=1e-9)
