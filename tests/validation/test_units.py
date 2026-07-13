"""Unit-consistency validation.

Unit confusion (GHz vs Hz, fF vs F, nA vs A) is the most common bug source in
superconducting-circuit design, so these tests pin down the netlist unit
registry and the dimensional correctness of the derived energies. They depend
only on ``core.netlist`` and the reference module -- no solver required.
"""

from __future__ import annotations

import math

import pytest
from core.netlist import Quantity, load, unit_dimension

from . import reference as ref


# --- Netlist Quantity / unit-registry consistency --------------------------
@pytest.mark.parametrize(
    "value, unit, expected_si",
    [
        (30.0, "nA", 30e-9),  # current
        (2.0, "fF", 2e-15),  # capacitance
        (70.0, "fF", 70e-15),
        (10.0, "kohm", 10e3),  # resistance
        (7.2, "GHz", 7.2e9),  # frequency
        (6.0, "mm", 6e-3),  # length
        (1.0, "V", 1.0),  # voltage
    ],
)
def test_quantity_to_si_scales_correctly(value, unit, expected_si):
    """Quantity.to_si() applies the correct SI scale factor for each unit."""
    assert math.isclose(Quantity(value, unit).to_si(), expected_si, rel_tol=1e-12)


def test_dimensionless_quantity_is_unscaled():
    """A dimensionless quality factor Q keeps its numeric value in SI."""
    q = Quantity(8000.0, "")
    assert q.dimension == "dimensionless"
    assert q.to_si() == 8000.0


@pytest.mark.parametrize(
    "unit, dimension",
    [
        ("nA", "current"),
        ("fF", "capacitance"),
        ("kohm", "resistance"),
        ("GHz", "frequency"),
        ("nH", "inductance"),
    ],
)
def test_unit_dimension_lookup(unit, dimension):
    """The registry maps each unit token to its physical dimension."""
    assert unit_dimension(unit) == dimension


def test_prefix_ladder_is_consistent_within_a_dimension():
    """fF/pF/nF differ by exactly 1000x steps, catching prefix mistakes."""
    ff = Quantity(1.0, "fF").to_si()
    pf = Quantity(1.0, "pF").to_si()
    nf = Quantity(1.0, "nF").to_si()
    assert math.isclose(pf / ff, 1000.0, rel_tol=1e-12)
    assert math.isclose(nf / pf, 1000.0, rel_tol=1e-12)


# --- Dimensional correctness of the derived junction energies --------------
def test_josephson_energy_units_are_frequency_and_scale_with_current():
    """Ej/h is a frequency (Hz) and is linear in Ic."""
    ej1 = ref.josephson_energy_hz(30e-9)
    ej2 = ref.josephson_energy_hz(60e-9)
    # Linear in Ic.
    assert math.isclose(ej2 / ej1, 2.0, rel_tol=1e-12)
    # Order-of-magnitude sanity: 30 nA junction -> ~15 GHz (a few GHz..tens).
    assert 1e9 < ej1 < 1e11


def test_charging_energy_units_and_inverse_capacitance_scaling():
    """Ec/h is a frequency (Hz) and scales as 1/C_Sigma."""
    ec1 = ref.charging_energy_hz(77e-15)
    ec2 = ref.charging_energy_hz(154e-15)
    assert math.isclose(ec1 / ec2, 2.0, rel_tol=1e-12)
    # 77 fF island -> a few hundred MHz.
    assert 1e8 < ec1 < 1e9


def test_ej_over_ec_is_dimensionless_and_unit_system_independent():
    """Ej/Ec must be identical whether computed in Hz or in GHz.

    This is the canonical unit-confusion trap: if one energy is accidentally in
    Hz and the other in GHz, the ratio is off by 1e9. Here we recompute Ec/Ej
    consistently and confirm the ratio is invariant to an overall 1e-9 rescale.
    """
    ej_hz = ref.josephson_energy_hz(ref.EXAMPLE_IC_A)
    ec_hz = ref.charging_energy_hz(ref.EXAMPLE_C_SIGMA_F)
    ratio_hz = ej_hz / ec_hz
    ratio_ghz = (ej_hz / 1e9) / (ec_hz / 1e9)
    assert math.isclose(ratio_hz, ratio_ghz, rel_tol=1e-12)
    # Reference transmon sits deep in the transmon regime.
    assert ratio_hz > 30.0


def test_example_netlist_parameters_carry_expected_units(examples_dir):
    """The example netlist declares physically sensible units per parameter."""
    nl = load(str(examples_dir / "transmon_readout.json"), validate=True)
    j1 = nl.element_by_id("J1")
    assert j1 is not None
    assert j1.params["Ic"].dimension == "current"
    assert j1.params["Cj"].dimension == "capacitance"
    assert j1.params["Rn"].dimension == "resistance"
    # And that the numeric magnitudes match what the reference module assumes.
    assert math.isclose(j1.params["Ic"].to_si(), ref.EXAMPLE_IC_A, rel_tol=1e-12)
    assert math.isclose(j1.params["Cj"].to_si(), ref.EXAMPLE_CJ_F, rel_tol=1e-12)
