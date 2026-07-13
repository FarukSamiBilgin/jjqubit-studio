"""Shared helpers for the netlist test-suite."""

from __future__ import annotations

from core.netlist import Connection, Element, Netlist, Quantity


def q(value: float, unit: str) -> Quantity:
    """Short alias for :class:`Quantity`."""
    return Quantity(value, unit)


def valid_netlist() -> Netlist:
    """Return a small but fully valid transmon-like netlist.

    Nodes: gnd, q, r. junction + shunt cap on the qubit node, coupling cap to a
    lumped resonator, plus a ground element. Every node has degree >= 2 and is
    connected to ground.
    """
    return Netlist(
        name="unit-test transmon",
        nodes=["gnd", "q", "r"],
        elements=[
            Element(
                "J1",
                "junction",
                {
                    "Ic": q(30.0, "nA"),
                    "Cj": q(2.0, "fF"),
                    "Rn": q(10.0, "kohm"),
                },
            ),
            Element("Cs", "capacitor", {"C": q(70.0, "fF")}),
            Element("Cg", "capacitor", {"C": q(5.0, "fF")}),
            Element("RES1", "resonator", {"f0": q(7.2, "GHz"), "Q": q(8000.0, "")}),
            Element("GND1", "ground", {}),
        ],
        connections=[
            Connection("J1", 0, "q"),
            Connection("J1", 1, "gnd"),
            Connection("Cs", 0, "q"),
            Connection("Cs", 1, "gnd"),
            Connection("Cg", 0, "q"),
            Connection("Cg", 1, "r"),
            Connection("RES1", 0, "r"),
            Connection("RES1", 1, "gnd"),
            Connection("GND1", 0, "gnd"),
        ],
    )
