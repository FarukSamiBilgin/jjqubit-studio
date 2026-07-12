"""Tests for core.solvers.classical.topology: RCSJ-bias and readout extraction."""
from __future__ import annotations

import pytest

from core.solvers.classical.topology import (
    TopologyError,
    extract_rcsj_topology,
    extract_readout_topology,
)


class TestExtractRcsjTopology:
    def test_finds_junction_and_current_source(self, rcsj_netlist):
        topo = extract_rcsj_topology(rcsj_netlist)
        assert topo.junction.id == "J1"
        assert topo.current_source.id == "Ib"
        assert topo.bias_node == "n1"
        assert topo.ground_node == "gnd"

    def test_collects_shunt_capacitor(self, rcsj_netlist):
        topo = extract_rcsj_topology(rcsj_netlist)
        assert topo.capacitor_ids == ("Cs",)

    def test_detects_inductor_without_including_it(self, rcsj_netlist):
        # L1 is wired to the bias node in examples/rcsj_bias.json; topology
        # extraction must surface it (for the HDF5 assumptions note) without
        # raising -- see rcsj.py module docstring for why it stays excluded
        # from the ODE itself.
        topo = extract_rcsj_topology(rcsj_netlist)
        assert topo.inductor_ids == ("L1",)

    def test_no_extra_shunt_resistor_in_bundled_example(self, rcsj_netlist):
        topo = extract_rcsj_topology(rcsj_netlist)
        assert topo.shunt_resistor_ids == ()

    def test_rejects_netlist_without_junction(self, transmon_netlist_no_junction):
        with pytest.raises(TopologyError, match="junction"):
            extract_rcsj_topology(transmon_netlist_no_junction)

    def test_rejects_netlist_without_current_source(self, transmon_netlist):
        # transmon_readout.json has a junction but no current_source.
        with pytest.raises(TopologyError, match="current_source"):
            extract_rcsj_topology(transmon_netlist)


class TestExtractReadoutTopology:
    def test_finds_resonator_and_termination(self, transmon_netlist):
        topo = extract_readout_topology(transmon_netlist)
        assert topo.resonator.id == "RES1"
        assert topo.active_node == "r"
        assert topo.transmission_line.id == "TL1"
        assert topo.termination.id == "Rload"

    def test_finds_coupling_capacitor_and_feedline_node(self, transmon_netlist):
        topo = extract_readout_topology(transmon_netlist)
        assert topo.coupling_capacitor_ids == ("Ck",)
        assert topo.feedline_node == "fin"
        assert topo.far_node == "fout"

    def test_rejects_netlist_without_resonator(self, rcsj_netlist):
        with pytest.raises(TopologyError, match="resonator"):
            extract_readout_topology(rcsj_netlist)


@pytest.fixture
def transmon_netlist_no_junction(transmon_netlist):
    """The transmon example with its junction element removed."""
    import copy

    netlist = copy.deepcopy(transmon_netlist)
    netlist.elements = [el for el in netlist.elements if el.type != "junction"]
    netlist.connections = [c for c in netlist.connections if c.element != "J1"]
    return netlist
