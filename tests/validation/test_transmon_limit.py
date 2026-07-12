"""Analytic-limit test #1: transmon limit (Ej/Ec >> 1), anharmonicity -> -Ec.

CLAUDE.md requires: "in the transmon limit (Ej/Ec >> 1) the anharmonicity should
come out approximately -Ec". This is an *asymptotic* statement. An important
validation subtlety encoded here: at the reference transmon's Ej/Ec ~ 59 the
absolute anharmonicity is ~13% LARGER in magnitude than Ec (it approaches -Ec
only from below as Ej/Ec -> infinity). A naive test asserting
`anharmonicity == -Ec` to a few percent would therefore encode WRONG physics and
wrongly reject a correct solver. We instead assert (a) the correct sign and
approximate magnitude at the reference ratio, and (b) monotone convergence
anharmonicity/(-Ec) -> 1 as Ej/Ec grows.

Grounding: from-scratch charge-basis diagonalization (this module's reference),
cross-checked against scqubits; Koch et al. 2007 eq. 2.5.
"""
from __future__ import annotations

import numpy as np
import pytest

from . import reference as ref


def test_scratch_reference_matches_scqubits():
    """Our from-scratch CPB diagonalization must agree with scqubits.

    If these two independent computations disagree, one of them is wrong and no
    downstream comparison can be trusted. They must match to ~kHz on GHz-scale
    transitions.
    """
    scq = pytest.importorskip("scqubits")
    ej = ref.josephson_energy_hz(ref.EXAMPLE_IC_A) / 1e9   # GHz for scqubits
    ec = ref.charging_energy_hz(ref.EXAMPLE_C_SIGMA_F) / 1e9
    tmon = scq.Transmon(EJ=ej, EC=ec, ng=0.0, ncut=40)
    evals = tmon.eigenvals(evals_count=3)
    e01_scq = (evals[1] - evals[0]) * 1e9
    e12_scq = (evals[2] - evals[1]) * 1e9

    r = ref.transmon_reference(ej * 1e9, ec * 1e9)
    assert np.isclose(r.e01_hz, e01_scq, rtol=0, atol=1e3)   # within 1 kHz
    assert np.isclose(r.e12_hz, e12_scq, rtol=0, atol=1e3)


def test_reference_transmon_anharmonicity_near_minus_ec():
    """Reference transmon: anharmonicity is negative and near -Ec (within 15%).

    At Ej/Ec ~ 59 the exact anharmonicity (~-285 MHz) is ~13% more negative than
    -Ec (~-252 MHz). We require the correct sign and agreement to 15%, which is
    the physically correct band -- NOT a tight equality.
    """
    r = ref.example_transmon_reference()
    assert r.anharmonicity_hz < 0.0                      # transmon is anharmonic downward
    assert r.ej_ec_ratio > 30.0                          # genuinely in transmon regime
    rel_err = abs(r.anharmonicity_hz / (-r.ec_hz) - 1.0)
    assert rel_err < 0.15
    # And it is more negative than -Ec (approaches from below), not less.
    assert r.anharmonicity_hz < -r.ec_hz


def test_anharmonicity_converges_to_minus_ec_as_ej_ec_grows():
    """anharmonicity/(-Ec) -> 1 monotonically as Ej/Ec increases.

    This is the actual content of "anharmonicity ~ -Ec in the transmon limit".
    We fix Ec and sweep Ej so Ej/Ec grows, and require the ratio to approach 1
    monotonically and reach within 3% at large Ej/Ec.
    """
    ec_hz = 0.25e9  # 250 MHz, representative
    ratios = [20.0, 50.0, 100.0, 300.0, 800.0]
    approach = []
    for ratio in ratios:
        r = ref.transmon_reference(ratio * ec_hz, ec_hz)
        approach.append(abs(r.anharmonicity_hz / (-ec_hz)))
    # Monotone decrease toward 1 (always >= 1: exact |alpha| >= Ec).
    for a in approach:
        assert a >= 1.0 - 1e-6
    assert all(x2 <= x1 + 1e-9 for x1, x2 in zip(approach, approach[1:]))
    # Deep in the transmon limit, within 3%.
    assert approach[-1] < 1.03


def test_e01_matches_koch_asymptotic_form():
    """E01 ~ sqrt(8 Ej Ec) - Ec (Koch 2007 eq. 2.5) to better than 1%."""
    r = ref.example_transmon_reference()
    e01_asym = np.sqrt(8.0 * r.ej_hz * r.ec_hz) - r.ec_hz
    assert np.isclose(r.e01_hz, e01_asym, rtol=0.01)
