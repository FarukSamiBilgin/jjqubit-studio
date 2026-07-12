"""Tests for Ej/Ec/Cg extraction (core.solvers.quantum.quantization).

Cross-checked by hand against the bundled example's parameters:
    J1: Ic=30nA, Cj=2fF, Rn=10kohm
    Cs: 70fF (shunt), Cg: 5fF (coupling to resonator)
    => C_sigma = Cj + Cs + Cg = 77 fF
    Ej = Phi_0/(2pi) * Ic = Ic / (4*pi*e)  ~= 14.90 GHz
    Ec = e^2 / (2*C_sigma*h)               ~= 0.2516 GHz
    Ej/Ec ~= 59.2  (deep transmon regime, matches Koch et al. 2007's typical
    experimental design range of a few tens to ~100)
"""
from __future__ import annotations

import math

import pytest
from scipy.constants import e as ELEMENTARY_CHARGE
from scipy.constants import h as PLANCK_H

from core.solvers.quantum.quantization import quantize_circuit
from core.solvers.quantum.topology import TopologyError
from helpers import make_transmon_only_netlist, make_transmon_resonator_netlist

FLUX_QUANTUM = PLANCK_H / (2.0 * ELEMENTARY_CHARGE)


def _hand_computed_ej_ghz(ic_amps: float) -> float:
    """Independent (non-shared-code) reference calculation for Ej."""
    ej_joules = (FLUX_QUANTUM / (2.0 * math.pi)) * ic_amps
    return ej_joules / PLANCK_H / 1e9


def _hand_computed_ec_ghz(c_sigma_farad: float) -> float:
    """Independent (non-shared-code) reference calculation for Ec."""
    ec_joules = ELEMENTARY_CHARGE**2 / (2.0 * c_sigma_farad)
    return ec_joules / PLANCK_H / 1e9


class TestQuantizeCircuitReferenceExample:
    def test_total_capacitance_sums_topology_not_hardcoded_ids(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        assert result.C_sigma_fF == pytest.approx(2.0 + 70.0 + 5.0, rel=1e-9)

    def test_coupling_capacitance_is_the_direct_bridge_only(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        # Ck (8fF) sits between r and fin, NOT between q and r -- must be excluded.
        assert result.Cg_fF == pytest.approx(5.0, rel=1e-9)

    def test_ej_matches_josephson_relation(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        expected = _hand_computed_ej_ghz(30.0e-9)
        assert result.Ej_GHz == pytest.approx(expected, rel=1e-9)
        # Sanity: real transmons commonly sit at Ej of order 10-30 GHz.
        assert 5.0 < result.Ej_GHz < 40.0

    def test_ec_matches_charging_energy_formula(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        expected = _hand_computed_ec_ghz(77e-15)
        assert result.Ec_GHz == pytest.approx(expected, rel=1e-9)
        # Sanity: real transmons commonly sit at Ec of order 100-400 MHz.
        assert 0.1 < result.Ec_GHz < 0.5

    def test_ej_over_ec_in_transmon_regime(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        assert result.Ej_over_Ec == pytest.approx(59.2, rel=0.02)
        assert result.Ej_over_Ec > 1.0  # firmly in the transmon (not CPB) regime

    def test_ic_and_island_node_passed_through(self, transmon_netlist):
        result = quantize_circuit(transmon_netlist)
        assert result.Ic_nA == pytest.approx(30.0, rel=1e-9)
        assert result.junction_id == "J1"
        assert result.island_node == "q"


class TestQuantizeCircuitUnitConversion:
    @pytest.mark.parametrize(
        "ic_value,ic_unit,expected_nA",
        [(30.0, "nA", 30.0), (0.03, "uA", 30.0), (30000.0, "pA", 30.0)],
    )
    def test_ic_unit_conversion_is_consistent(self, ic_value, ic_unit, expected_nA):
        # Quantity.to_si() handles unit conversion (frozen contract); this
        # test just confirms quantize_circuit does not double-convert or
        # silently assume a specific input unit token.
        from core.netlist import Quantity

        nl = make_transmon_resonator_netlist()
        nl.element_by_id("J1").params["Ic"] = Quantity(ic_value, ic_unit)
        result = quantize_circuit(nl)
        assert result.Ic_nA == pytest.approx(expected_nA, rel=1e-9)


class TestQuantizeCircuitScaling:
    def test_ec_scales_inversely_with_total_capacitance(self):
        nl_small_c = make_transmon_resonator_netlist(Cs_fF=10.0)
        nl_large_c = make_transmon_resonator_netlist(Cs_fF=100.0)
        small = quantize_circuit(nl_small_c)
        large = quantize_circuit(nl_large_c)
        # Ec ~ 1/C_sigma: quadrupling-ish C_sigma should shrink Ec by the
        # same ratio (within floating point).
        ratio_c = small.C_sigma_fF / large.C_sigma_fF
        ratio_ec = large.Ec_GHz / small.Ec_GHz
        assert ratio_ec == pytest.approx(ratio_c, rel=1e-9)

    def test_ej_scales_linearly_with_ic(self):
        nl_small_ic = make_transmon_resonator_netlist(Ic_nA=10.0)
        nl_large_ic = make_transmon_resonator_netlist(Ic_nA=40.0)
        small = quantize_circuit(nl_small_ic)
        large = quantize_circuit(nl_large_ic)
        assert large.Ej_GHz / small.Ej_GHz == pytest.approx(4.0, rel=1e-9)

    def test_no_coupling_capacitor_gives_zero_cg(self):
        nl = make_transmon_resonator_netlist()
        nl.elements = [el for el in nl.elements if el.id != "Cg"]
        nl.connections = [c for c in nl.connections if c.element != "Cg"]
        result = quantize_circuit(nl)
        assert result.Cg_fF == 0.0
        # C_sigma should drop by exactly Cg's contribution too.
        assert result.C_sigma_fF == pytest.approx(2.0 + 70.0, rel=1e-9)


class TestQuantizeCircuitTopologyErrors:
    def test_missing_resonator_raises_topology_error(self, rcsj_netlist):
        with pytest.raises(TopologyError):
            quantize_circuit(rcsj_netlist)

    def test_missing_resonator_raises_topology_error_bare_transmon(self):
        with pytest.raises(TopologyError):
            quantize_circuit(make_transmon_only_netlist())
