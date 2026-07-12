"""Analytic-limit test #2: Ej/Ec -> 0 approaches Cooper-pair-box behavior.

CLAUDE.md requires: "in the limit Ej/Ec -> 0 the system approaches Cooper-pair-
box behavior". Two independent signatures of the CPB (charge) regime are checked
against the from-scratch charge-basis reference:

1. At Ej = 0 the eigen-energies are exactly the bare charging parabolas
   ``E_n = 4 Ec (n - ng)^2`` -- the pure charge states.
2. The charge dispersion (sensitivity of a level to the offset charge ng) is
   LARGE and O(Ec) in the CPB limit and becomes exponentially suppressed as
   Ej/Ec grows -- the defining feature that distinguishes a transmon from a CPB
   (Koch 2007 eq. 2.5, Fig. 2).

Grounding: from-scratch charge-basis diagonalization.
"""
from __future__ import annotations

import numpy as np

from . import reference as ref


def test_zero_ej_gives_bare_charge_parabolas():
    """With Ej = 0 the spectrum is exactly 4 Ec (n - ng)^2 (pure charge states)."""
    ec_hz = 0.25e9
    ng = 0.0
    evals, _ = ref.cpb_eigensystem_hz(0.0, ec_hz, ng=ng, ncut=20)
    # Expected lowest levels: n = 0, +/-1, +/-2, ...  -> 0, 4Ec, 4Ec, 16Ec, 16Ec
    expected = np.sort(
        [4.0 * ec_hz * (n - ng) ** 2 for n in range(-20, 21)]
    )
    assert np.allclose(evals, expected, rtol=0, atol=1e-3)  # sub-mHz agreement


def test_charge_dispersion_grows_as_ej_ec_decreases():
    """Charge dispersion of the ground level increases monotonically as Ej/Ec->0."""
    ec_hz = 0.20e9
    ratios = [50.0, 10.0, 3.0, 1.0, 0.3, 0.1]  # decreasing Ej/Ec
    disp = [ref.charge_dispersion_hz(r * ec_hz, ec_hz, level=0) for r in ratios]
    # Strictly increasing dispersion as Ej/Ec decreases.
    assert all(d2 > d1 for d1, d2 in zip(disp, disp[1:]))


def test_cpb_limit_dispersion_is_order_ec():
    """In the deep CPB limit the charge dispersion is O(Ec), not exponentially small."""
    ec_hz = 0.20e9
    disp = ref.charge_dispersion_hz(0.1 * ec_hz, ec_hz, level=0)
    # Should be a sizeable fraction of Ec (here comparable to Ec), i.e. the level
    # is strongly charge-sensitive -- a CPB, not a transmon.
    assert disp > 0.5 * ec_hz


def test_transmon_dispersion_is_exponentially_suppressed():
    """At Ej/Ec >> 1 the charge dispersion is tiny compared to Ec (transmon)."""
    ec_hz = 0.20e9
    disp = ref.charge_dispersion_hz(50.0 * ec_hz, ec_hz, level=0)
    # Exponentially suppressed: << 1e-3 of Ec.
    assert disp < 1e-3 * ec_hz
