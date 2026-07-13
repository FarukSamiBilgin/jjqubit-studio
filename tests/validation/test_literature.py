"""Reference-transmon comparison against known literature values / scaling laws.

Grounded in J. Koch et al., PRA 76, 042319 (2007). We deliberately anchor to the
paper's *analytic expressions and scaling laws* (eqs. 2.5) and to the well-known
empirical operating ranges of transmons, rather than to a single fabricated
"table value":

* E01 = sqrt(8 Ej Ec) - Ec + O(Ec) -- the transmon transition frequency.
* Relative anharmonicity alpha_r = alpha / E01 ~ -(8 Ej/Ec)^(-1/2): scales as
  (Ej/Ec)^(-1/2).
* Real transmons operate at a few GHz with anharmonicity of order -200..-350 MHz.

These give an independent sanity envelope for whatever solver-quantum computes
from examples/transmon_readout.json.
"""

from __future__ import annotations

import numpy as np

from . import reference as ref


def test_reference_transmon_frequency_in_operating_band():
    """E01 of the example transmon lands in the standard 4-6 GHz operating band."""
    r = ref.example_transmon_reference()
    assert 4.0e9 < r.e01_hz < 6.0e9


def test_reference_transmon_anharmonicity_in_typical_range():
    """Anharmonicity is in the typical measured -200..-350 MHz range."""
    r = ref.example_transmon_reference()
    assert -0.35e9 < r.anharmonicity_hz < -0.20e9


def test_relative_anharmonicity_follows_koch_scaling():
    """alpha_r ~ (Ej/Ec)^(-1/2): the ratio of alpha_r at two Ej/Ec matches sqrt.

    Koch 2007 eq. 2.5. We compare Ej/Ec = 100 vs 400 (factor 4); alpha_r should
    change by ~sqrt(4) = 2. The (Ej/Ec)^(-1/2) law is asymptotic, so even deep in
    the transmon regime a finite-ratio correction of several percent remains;
    tolerance 12% reflects that honestly while still pinning the sqrt scaling.
    """
    ec_hz = 0.25e9
    r_lo = ref.transmon_reference(100.0 * ec_hz, ec_hz)
    r_hi = ref.transmon_reference(400.0 * ec_hz, ec_hz)
    ar_lo = r_lo.anharmonicity_hz / r_lo.e01_hz
    ar_hi = r_hi.anharmonicity_hz / r_hi.e01_hz
    assert np.isclose(ar_lo / ar_hi, 2.0, rtol=0.12)


def test_reference_energies_have_expected_magnitudes():
    """Pin the independently computed Ej/h, Ec/h, E01 for the example transmon.

    These are this suite's documented ground-truth numbers (Cj+Cs+Cg = 77 fF
    convention) for solver-quantum to reproduce from the same netlist:
        Ej/h  ~ 14.90 GHz
        Ec/h  ~ 251.6 MHz
        E01   ~ 5.211 GHz
        alpha ~ -285.0 MHz
    """
    r = ref.example_transmon_reference()
    assert np.isclose(r.ej_hz, 14.90e9, rtol=0.01)
    assert np.isclose(r.ec_hz, 251.6e6, rtol=0.01)
    assert np.isclose(r.e01_hz, 5.211e9, rtol=0.01)
    assert np.isclose(r.anharmonicity_hz, -285.0e6, rtol=0.02)


def test_capacitance_convention_both_give_valid_transmons():
    """Document the C_Sigma convention ambiguity (Cj+Cs vs Cj+Cs+Cg).

    solver-quantum derives Ec from a capacitance matrix; depending on how the
    coupling capacitor Cg is folded in, C_Sigma is 72 fF (Cj+Cs) or 77 fF
    (Cj+Cs+Cg). Both yield a valid transmon (Ej/Ec > 30, few-GHz E01), but Ec
    differs by ~7%. This test records that both are physically reasonable so the
    eventual solver comparison can pick the matching convention rather than
    silently disagreeing by 7%.
    """
    ej_hz = ref.josephson_energy_hz(ref.EXAMPLE_IC_A)
    for c_sigma in (
        ref.EXAMPLE_CJ_F + ref.EXAMPLE_CS_F,  # 72 fF
        ref.EXAMPLE_CJ_F + ref.EXAMPLE_CS_F + ref.EXAMPLE_CG_F,  # 77 fF
    ):
        ec_hz = ref.charging_energy_hz(c_sigma)
        r = ref.transmon_reference(ej_hz, ec_hz)
        assert r.ej_ec_ratio > 30.0
        assert 4.0e9 < r.e01_hz < 6.0e9
    # And the two conventions differ by the expected ~7%.
    ec_72 = ref.charging_energy_hz(72e-15)
    ec_77 = ref.charging_energy_hz(77e-15)
    assert np.isclose(ec_72 / ec_77, 77.0 / 72.0, rtol=1e-6)
