"""Tests for the transmon spectrum (core.solvers.quantum.spectrum).

These are the CLAUDE.md-mandated "known analytic limit" self-checks for this
solver (see CLAUDE.md's "Fizik dogrulama kurali" and docs/task.md's
acceptance criteria):

    - Transmon limit (Ej/Ec >> 1): anharmonicity -> -Ec, monotonically, as
      Ej/Ec grows (Koch et al., PRA 76, 042319 (2007)).
    - Ej/Ec -> 0 limit: the system should behave like a Cooper-pair box,
      i.e. show strong (~GHz-scale) charge dispersion of E01 with ng, unlike
      the transmon regime where E01 is nearly ng-independent.

All physics is computed by scqubits (CLAUDE.md's "Yapmayacaklarimiz" #2 --
we do not reimplement the CPB/transmon Hamiltonian); these tests check that
OUR wrapper reports scqubits' results correctly and that the well-known
physical trends hold.
"""
from __future__ import annotations

import math

import pytest
import scqubits as scq

from core.solvers.quantum.spectrum import compute_transmon_spectrum


class TestTransmonLimitAnharmonicity:
    """Ej/Ec >> 1: anharmonicity should converge to -Ec."""

    @pytest.mark.parametrize("ratio", [10.0, 30.0, 60.0, 150.0])
    def test_anharmonicity_is_negative_and_of_order_ec(self, ratio):
        Ec = 0.25
        Ej = ratio * Ec
        spectrum = compute_transmon_spectrum(Ej, Ec)
        assert spectrum.anharmonicity_GHz < 0.0
        # In the transmon regime the anharmonicity magnitude is O(Ec), not
        # wildly different (it should never exceed Ec by more than a small
        # multiplicative factor, nor be a tiny fraction of it).
        assert 0.5 * Ec < abs(spectrum.anharmonicity_GHz) < 3.0 * Ec

    def test_anharmonicity_over_ec_converges_to_one_as_ratio_grows(self):
        Ec = 0.25
        ratios = [10.0, 30.0, 60.0, 150.0, 500.0]
        deviations = []
        for ratio in ratios:
            spectrum = compute_transmon_spectrum(ratio * Ec, Ec)
            deviations.append(abs(spectrum.anharmonicity_GHz / (-Ec) - 1.0))
        # Deviation from the ideal -Ec limit should shrink monotonically as
        # Ej/Ec grows (this is the actual "convergence to the known analytic
        # limit" check CLAUDE.md asks for).
        for earlier, later in zip(deviations, deviations[1:]):
            assert later < earlier
        # And it should get tight (single-digit percent) at large Ej/Ec.
        assert deviations[-1] < 0.05

    def test_reference_example_parameters_are_in_transmon_regime(self):
        # examples/transmon_readout.json: Ej~=14.9 GHz, Ec~=0.2516 GHz.
        spectrum = compute_transmon_spectrum(14.900505323300266, 0.2515614198007678)
        assert spectrum.anharmonicity_GHz == pytest.approx(-0.2516, abs=0.05)
        ratio = abs(spectrum.anharmonicity_GHz) / 0.2515614198007678
        assert 1.0 < ratio < 1.5  # order-Ec, modest positive correction, as expected


class TestCooperPairBoxLimit:
    """Ej/Ec -> 0: should show strong charge dispersion (unlike a transmon)."""

    def test_deep_cpb_shows_large_charge_dispersion(self):
        Ec = 1.0
        Ej = 0.05 * Ec  # Ej/Ec = 0.05, deep charge-qubit/CPB regime
        spectrum_ng0 = compute_transmon_spectrum(Ej, Ec, ng=0.0)
        spectrum_ng_half = compute_transmon_spectrum(Ej, Ec, ng=0.5)
        dispersion = abs(spectrum_ng0.E01_GHz - spectrum_ng_half.E01_GHz)
        # In the CPB limit E01 swings from ~2Ec*(1-2*ng)-ish at ng=0 down to
        # ~Ej near the charge-degeneracy point ng=0.5 -- a large (GHz-scale)
        # swing, in stark contrast to the transmon's near-flat E01(ng).
        assert dispersion > 0.5

    def test_deep_transmon_shows_negligible_charge_dispersion(self):
        Ec = 0.25
        Ej = 100.0 * Ec  # deep transmon regime
        spectrum_ng0 = compute_transmon_spectrum(Ej, Ec, ng=0.0)
        spectrum_ng_half = compute_transmon_spectrum(Ej, Ec, ng=0.5)
        dispersion = abs(spectrum_ng0.E01_GHz - spectrum_ng_half.E01_GHz)
        # Exponentially suppressed charge dispersion is the entire point of
        # the transmon design (Koch et al. 2007); should be tiny (MHz-scale
        # or smaller), not the GHz-scale swing seen in the CPB limit.
        assert dispersion < 1e-3

    def test_charge_dispersion_shrinks_as_ej_over_ec_grows(self):
        Ec = 0.25
        dispersions = []
        for ratio in [0.1, 1.0, 10.0, 100.0]:
            Ej = ratio * Ec
            d = abs(
                compute_transmon_spectrum(Ej, Ec, ng=0.0).E01_GHz
                - compute_transmon_spectrum(Ej, Ec, ng=0.5).E01_GHz
            )
            dispersions.append(d)
        for earlier, later in zip(dispersions, dispersions[1:]):
            assert later < earlier


class TestSpectrumApiContract:
    def test_energy_levels_are_sorted_and_start_at_zero(self):
        spectrum = compute_transmon_spectrum(15.0, 0.25, n_levels=6)
        levels = spectrum.energy_levels_GHz
        assert levels[0] == 0.0
        assert all(b >= a for a, b in zip(levels, levels[1:]))
        assert len(levels) == 6

    def test_e01_matches_first_energy_level(self):
        spectrum = compute_transmon_spectrum(15.0, 0.25)
        assert spectrum.E01_GHz == pytest.approx(spectrum.energy_levels_GHz[1], rel=1e-9)

    def test_anharmonicity_matches_level_differences(self):
        spectrum = compute_transmon_spectrum(15.0, 0.25)
        levels = spectrum.energy_levels_GHz
        expected = (levels[2] - levels[1]) - (levels[1] - levels[0])
        assert spectrum.anharmonicity_GHz == pytest.approx(expected, rel=1e-9)

    def test_underlying_transmon_is_a_real_scqubits_instance(self):
        spectrum = compute_transmon_spectrum(15.0, 0.25)
        assert isinstance(spectrum.transmon, scq.Transmon)

    @pytest.mark.parametrize("n_levels", [0, 1, 2])
    def test_too_few_levels_rejected(self, n_levels):
        with pytest.raises(ValueError):
            compute_transmon_spectrum(15.0, 0.25, n_levels=n_levels)

    @pytest.mark.parametrize("Ej,Ec", [(0.0, 0.25), (15.0, 0.0), (-1.0, 0.25), (15.0, -0.25)])
    def test_nonpositive_energies_rejected(self, Ej, Ec):
        with pytest.raises(ValueError):
            compute_transmon_spectrum(Ej, Ec)

    def test_ncut_convergence_is_not_sensitive_to_deep_transmon_regime(self):
        # Guards the adaptive-ncut heuristic in spectrum.py: a much deeper
        # transmon than the bundled example should still give a converged
        # (finite, sane) anharmonicity, not a numerical artifact.
        spectrum = compute_transmon_spectrum(Ej_GHz=50.0, Ec_GHz=0.2)
        assert math.isfinite(spectrum.anharmonicity_GHz)
        assert -0.5 < spectrum.anharmonicity_GHz < 0.0
