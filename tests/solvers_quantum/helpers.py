"""Shared netlist builders for the quantum-solver test-suite.

Mirrors the convention in ``tests/netlist/helpers.py`` (plain module,
imported directly by test files -- not fixtures).
"""
from __future__ import annotations

from core.netlist import Connection, Element, Netlist, Quantity


def q(value: float, unit: str) -> Quantity:
    """Short alias for :class:`Quantity`."""
    return Quantity(value, unit)


def make_transmon_only_netlist(
    *, Ic_nA: float = 30.0, Cj_fF: float = 2.0, Rn_kohm: float = 10.0, Cs_fF: float = 70.0
) -> Netlist:
    """Build a minimal junction+shunt-capacitor netlist with NO resonator.

    Handy for topology-error tests that need a valid, groundable circuit
    that nonetheless lacks a resonator.
    """
    return Netlist(
        name="bare transmon, no resonator",
        nodes=["gnd", "q"],
        elements=[
            Element(
                id="J1",
                type="junction",
                params={
                    "Ic": q(Ic_nA, "nA"),
                    "Cj": q(Cj_fF, "fF"),
                    "Rn": q(Rn_kohm, "kohm"),
                },
            ),
            Element(id="Cs", type="capacitor", params={"C": q(Cs_fF, "fF")}),
            Element(id="GND1", type="ground", params={}),
        ],
        connections=[
            Connection("J1", 0, "q"),
            Connection("J1", 1, "gnd"),
            Connection("Cs", 0, "q"),
            Connection("Cs", 1, "gnd"),
            Connection("GND1", 0, "gnd"),
        ],
    )


def make_transmon_resonator_netlist(
    *,
    Ic_nA: float = 30.0,
    Cj_fF: float = 2.0,
    Rn_kohm: float = 10.0,
    Cs_fF: float = 70.0,
    Cg_fF: float = 5.0,
    f0_GHz: float = 7.2,
    Q: float = 8000.0,
) -> Netlist:
    """Build a minimal transmon + directly-coupled resonator netlist.

    A smaller, fully self-contained alternative to
    ``examples/transmon_readout.json`` (no feedline/transmission line), handy
    for parametrized quantization/dispersive tests that need to vary Ic, Cj,
    Cs, Cg, f0 independently.
    """
    return Netlist(
        name="minimal transmon + resonator",
        nodes=["gnd", "q", "r"],
        elements=[
            Element(
                id="J1",
                type="junction",
                params={
                    "Ic": q(Ic_nA, "nA"),
                    "Cj": q(Cj_fF, "fF"),
                    "Rn": q(Rn_kohm, "kohm"),
                },
            ),
            Element(id="Cs", type="capacitor", params={"C": q(Cs_fF, "fF")}),
            Element(id="Cg", type="capacitor", params={"C": q(Cg_fF, "fF")}),
            Element(
                id="RES1",
                type="resonator",
                params={"f0": q(f0_GHz, "GHz"), "Q": q(Q, "")},
            ),
            Element(id="GND1", type="ground", params={}),
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
