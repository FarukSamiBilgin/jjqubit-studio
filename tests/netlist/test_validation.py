"""Tests for each netlist validation failure mode.

Every test starts from a known-valid netlist, breaks exactly one thing, and
asserts that validation flags it (and names the offender in the message).
"""

from __future__ import annotations

import pytest
from core.netlist import (
    Connection,
    Element,
    Quantity,
    ValidationError,
    collect_errors,
    validate,
)
from helpers import valid_netlist


def q(v, u):
    return Quantity(v, u)


def _messages(nl):
    return " || ".join(collect_errors(nl))


def test_valid_netlist_passes():
    nl = valid_netlist()
    assert collect_errors(nl) == []
    validate(nl)  # must not raise


def test_missing_ground_detected():
    nl = valid_netlist()
    nl.elements = [e for e in nl.elements if e.type != "ground"]
    nl.connections = [c for c in nl.connections if c.element != "GND1"]
    msg = _messages(nl)
    assert "ground" in msg.lower()
    with pytest.raises(ValidationError):
        validate(nl)


def test_floating_node_detected():
    nl = valid_netlist()
    # Declare an extra node that nothing connects to.
    nl.nodes.append("dangling")
    msg = _messages(nl)
    assert "dangling" in msg
    assert "floating" in msg.lower()


def test_degree_one_node_is_floating():
    nl = valid_netlist()
    # Add a node touched by only a single terminal.
    nl.nodes.append("tip")
    nl.elements.append(Element("Cx", "capacitor", {"C": q(1.0, "fF")}))
    nl.connections.append(Connection("Cx", 0, "tip"))
    nl.connections.append(Connection("Cx", 1, "gnd"))
    msg = _messages(nl)
    assert "'tip'" in msg and "floating" in msg.lower()


def test_missing_required_parameter_detected():
    nl = valid_netlist()
    j1 = nl.element_by_id("J1")
    del j1.params["Ic"]  # junction now missing its critical current
    msg = _messages(nl)
    assert "J1" in msg and "Ic" in msg


def test_unknown_element_type_detected():
    nl = valid_netlist()
    nl.elements.append(Element("X1", "flux_qubit", {}))
    nl.nodes.append("x")
    nl.connections.append(Connection("X1", 0, "x"))
    nl.connections.append(Connection("X1", 1, "gnd"))
    msg = _messages(nl)
    assert "X1" in msg and "flux_qubit" in msg
    assert "unknown element type" in msg.lower()


def test_unknown_unit_via_wrong_dimension_detected():
    # A known unit but the WRONG physical dimension for the parameter
    # (Ic in GHz instead of a current). This is the classic unit-confusion bug.
    nl = valid_netlist()
    j1 = nl.element_by_id("J1")
    j1.params["Ic"] = q(5.0, "GHz")
    msg = _messages(nl)
    assert "Ic" in msg and "frequency" in msg and "current" in msg


def test_unknown_parameter_detected():
    nl = valid_netlist()
    nl.element_by_id("Cs").params["bogus"] = q(1.0, "fF")
    msg = _messages(nl)
    assert "bogus" in msg and "unknown parameter" in msg.lower()


def test_connection_to_undeclared_node_detected():
    nl = valid_netlist()
    nl.connections.append(Connection("Cs", 0, "ghost"))
    # Cs terminal 0 is now double-bound too, but the undeclared node is the point.
    msg = _messages(nl)
    assert "ghost" in msg and "undeclared" in msg.lower()


def test_connection_to_unknown_element_detected():
    nl = valid_netlist()
    nl.connections.append(Connection("NOPE", 0, "gnd"))
    msg = _messages(nl)
    assert "NOPE" in msg and "unknown element" in msg.lower()


def test_terminal_out_of_range_detected():
    nl = valid_netlist()
    nl.connections.append(Connection("Cs", 5, "gnd"))
    msg = _messages(nl)
    assert "Cs" in msg and "out of range" in msg.lower()


def test_unconnected_terminal_detected():
    nl = valid_netlist()
    # Drop one of Cg's terminal bindings, leaving terminal 1 unconnected.
    nl.connections = [
        c for c in nl.connections if not (c.element == "Cg" and c.terminal == 1)
    ]
    msg = _messages(nl)
    assert "Cg" in msg and "not connected" in msg.lower()


def test_double_bound_terminal_detected():
    nl = valid_netlist()
    nl.connections.append(Connection("Cg", 0, "gnd"))  # terminal 0 bound twice
    msg = _messages(nl)
    assert "Cg" in msg and "connected 2 times" in msg


def test_duplicate_element_id_detected():
    nl = valid_netlist()
    nl.elements.append(Element("J1", "capacitor", {"C": q(1.0, "fF")}))
    msg = _messages(nl)
    assert "duplicate element id" in msg.lower() and "J1" in msg


def test_duplicate_node_id_detected():
    nl = valid_netlist()
    nl.nodes.append("gnd")
    msg = _messages(nl)
    assert "duplicate node id" in msg.lower() and "gnd" in msg


def test_isolated_subcircuit_detected():
    nl = valid_netlist()
    # Two nodes wired to each other but not to ground.
    nl.nodes.extend(["iso1", "iso2"])
    nl.elements.append(Element("Ciso", "capacitor", {"C": q(1.0, "fF")}))
    nl.elements.append(Element("Liso", "inductor", {"L": q(1.0, "nH")}))
    nl.connections.extend(
        [
            Connection("Ciso", 0, "iso1"),
            Connection("Ciso", 1, "iso2"),
            Connection("Liso", 0, "iso1"),
            Connection("Liso", 1, "iso2"),
        ]
    )
    msg = _messages(nl)
    assert "not electrically connected to ground" in msg.lower()


def test_validation_error_collects_multiple_problems():
    nl = valid_netlist()
    del nl.element_by_id("J1").params["Ic"]
    nl.elements = [e for e in nl.elements if e.type != "ground"]
    nl.connections = [c for c in nl.connections if c.element != "GND1"]
    with pytest.raises(ValidationError) as excinfo:
        validate(nl)
    assert len(excinfo.value.errors) >= 2
