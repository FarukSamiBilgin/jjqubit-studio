"""Tests for topology extraction (core.solvers.quantum.topology).

These verify the solver derives qubit/resonator/coupling structure from
netlist WIRING (nodes_of / terminals_on_node / ground_nodes), never from
hardcoded element ids -- so a differently-named-but-isomorphic netlist would
be handled identically.
"""

from __future__ import annotations

import pytest
from core.netlist import Connection, Element, Netlist, Quantity
from core.solvers.quantum.topology import (
    TopologyError,
    extract_coupling_topology,
    extract_qubit_topology,
    extract_resonator_topology,
)
from quantum_helpers import make_transmon_only_netlist, make_transmon_resonator_netlist


class TestQubitTopology:
    def test_finds_junction_and_island_node(self, transmon_netlist):
        qubit = extract_qubit_topology(transmon_netlist)
        assert qubit.junction.id == "J1"
        assert qubit.island_node == "q"
        assert qubit.ground_node == "gnd"

    def test_capacitor_ids_are_every_capacitor_on_the_island_node(
        self, transmon_netlist
    ):
        qubit = extract_qubit_topology(transmon_netlist)
        # In examples/transmon_readout.json, node "q" also carries the shunt
        # cap Cs and the coupling cap Cg (but NOT Ck, which sits on node "r").
        assert set(qubit.capacitor_ids) == {"Cs", "Cg"}

    def test_topology_is_wiring_based_not_id_based(self):
        # Rename every id/node relative to the bundled example; extraction
        # must still work purely from the connection graph.
        nl = Netlist(
            name="renamed",
            nodes=["earth", "island"],
            elements=[
                Element(
                    id="weird_name_42",
                    type="junction",
                    params={
                        "Ic": Quantity(30.0, "nA"),
                        "Cj": Quantity(2.0, "fF"),
                        "Rn": Quantity(10.0, "kohm"),
                    },
                ),
                Element(
                    id="shunt", type="capacitor", params={"C": Quantity(70.0, "fF")}
                ),
                Element(id="gnd_marker", type="ground", params={}),
            ],
            connections=[
                Connection("weird_name_42", 0, "island"),
                Connection("weird_name_42", 1, "earth"),
                Connection("shunt", 0, "island"),
                Connection("shunt", 1, "earth"),
                Connection("gnd_marker", 0, "earth"),
            ],
        )
        qubit = extract_qubit_topology(nl)
        assert qubit.junction.id == "weird_name_42"
        assert qubit.island_node == "island"
        assert qubit.ground_node == "earth"
        assert qubit.capacitor_ids == ("shunt",)

    def test_no_junction_raises(self):
        nl = Netlist(
            name="no junction",
            nodes=["gnd"],
            elements=[Element(id="GND1", type="ground", params={})],
            connections=[Connection("GND1", 0, "gnd")],
        )
        with pytest.raises(TopologyError, match="no 'junction'"):
            extract_qubit_topology(nl)

    def test_two_junctions_raises(self):
        nl = make_transmon_only_netlist()
        nl.elements.append(
            Element(
                id="J2",
                type="junction",
                params={
                    "Ic": Quantity(30.0, "nA"),
                    "Cj": Quantity(2.0, "fF"),
                    "Rn": Quantity(10.0, "kohm"),
                },
            )
        )
        nl.connections.append(Connection("J2", 0, "q"))
        nl.connections.append(Connection("J2", 1, "gnd"))
        with pytest.raises(TopologyError, match="2 junctions"):
            extract_qubit_topology(nl)

    def test_junction_not_grounded_raises(self):
        # Both junction terminals on non-ground nodes: no unambiguous island.
        nl = Netlist(
            name="floating junction",
            nodes=["gnd", "a", "b"],
            elements=[
                Element(
                    id="J1",
                    type="junction",
                    params={
                        "Ic": Quantity(30.0, "nA"),
                        "Cj": Quantity(2.0, "fF"),
                        "Rn": Quantity(10.0, "kohm"),
                    },
                ),
                Element(id="GND1", type="ground", params={}),
                # Ground something unrelated so ground_nodes() isn't empty.
                Element(id="Cs", type="capacitor", params={"C": Quantity(1.0, "fF")}),
            ],
            connections=[
                Connection("J1", 0, "a"),
                Connection("J1", 1, "b"),
                Connection("GND1", 0, "gnd"),
                Connection("Cs", 0, "gnd"),
                Connection("Cs", 1, "a"),
            ],
        )
        with pytest.raises(TopologyError, match="junction 'J1' is wired"):
            extract_qubit_topology(nl)


class TestResonatorTopology:
    def test_finds_resonator_and_active_node(self, transmon_netlist):
        resonator = extract_resonator_topology(transmon_netlist)
        assert resonator.resonator.id == "RES1"
        assert resonator.active_node == "r"
        assert resonator.ground_node == "gnd"

    def test_no_resonator_raises(self, rcsj_netlist):
        with pytest.raises(TopologyError, match="no 'resonator'"):
            extract_resonator_topology(rcsj_netlist)

    def test_no_resonator_raises_bare_transmon(self):
        with pytest.raises(TopologyError, match="no 'resonator'"):
            extract_resonator_topology(make_transmon_only_netlist())


class TestCouplingTopology:
    def test_finds_direct_coupling_capacitor(self, transmon_netlist):
        qubit = extract_qubit_topology(transmon_netlist)
        resonator = extract_resonator_topology(transmon_netlist)
        coupling = extract_coupling_topology(transmon_netlist, qubit, resonator)
        assert coupling.capacitor_ids == ("Cg",)

    def test_no_direct_coupling_gives_empty_tuple(self):
        # Qubit and resonator both present, but no capacitor bridges them.
        nl = make_transmon_resonator_netlist()
        # Remove the Cg element and its connections to decouple qubit/resonator.
        nl.elements = [el for el in nl.elements if el.id != "Cg"]
        nl.connections = [c for c in nl.connections if c.element != "Cg"]
        qubit = extract_qubit_topology(nl)
        resonator = extract_resonator_topology(nl)
        coupling = extract_coupling_topology(nl, qubit, resonator)
        assert coupling.capacitor_ids == ()
