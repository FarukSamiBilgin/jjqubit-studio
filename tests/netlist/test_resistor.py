"""Tests for the `resistor` element type.

Added per lead addendum to Task #1: the feedline in examples/transmon_readout
needs a real matched-load termination (not a bare capacitor) for solver-classical's
S21 computation, so `resistor` (terminals [a, b], single param R: resistance)
was added to ELEMENT_TYPES.
"""
from __future__ import annotations

import pytest

from core.netlist import (
    ELEMENT_TYPES,
    Connection,
    Element,
    Quantity,
    ValidationError,
    collect_errors,
    dumps,
    loads,
    validate,
)

from helpers import q, valid_netlist


def _with_resistor(nl, **params):
    """Attach a resistor between 'q' and 'gnd' (both already degree->=2 nodes)."""
    nl.elements.append(Element("R1", "resistor", params))
    nl.connections.append(Connection("R1", 0, "q"))
    nl.connections.append(Connection("R1", 1, "gnd"))
    return nl


def test_resistor_is_registered_with_two_terminals_and_R_param():
    etype = ELEMENT_TYPES["resistor"]
    assert etype.terminals == ("a", "b")
    assert etype.n_terminals == 2
    spec = etype.param("R")
    assert spec is not None
    assert spec.dimension == "resistance"
    assert spec.required is True


def test_valid_resistor_passes_validation():
    nl = _with_resistor(valid_netlist(), R=q(50.0, "ohm"))
    assert collect_errors(nl) == []
    validate(nl)  # must not raise


def test_resistor_round_trips():
    nl = _with_resistor(valid_netlist(), R=q(50.0, "ohm"))
    assert loads(dumps(nl)) == nl
    r1 = loads(dumps(nl)).element_by_id("R1")
    assert r1.params["R"].unit == "ohm"
    assert r1.params["R"].value == 50.0


def test_resistor_missing_required_param_detected():
    nl = _with_resistor(valid_netlist())  # no R param at all
    msg = " || ".join(collect_errors(nl))
    assert "R1" in msg and "R" in msg and "missing required" in msg.lower()
    with pytest.raises(ValidationError):
        validate(nl)


def test_resistor_wrong_dimension_detected():
    # Classic unit-confusion bug: R given in a capacitance unit instead of ohm.
    nl = _with_resistor(valid_netlist(), R=q(50.0, "fF"))
    msg = " || ".join(collect_errors(nl))
    assert "R1" in msg and "resistance" in msg and "capacitance" in msg


def test_resistor_unknown_parameter_detected():
    nl = _with_resistor(valid_netlist(), R=q(50.0, "ohm"), bogus=q(1.0, "ohm"))
    msg = " || ".join(collect_errors(nl))
    assert "bogus" in msg and "unknown parameter" in msg.lower()


def test_resistor_terminal_count_enforced():
    nl = valid_netlist()
    nl.elements.append(Element("R1", "resistor", {"R": q(50.0, "ohm")}))
    nl.connections.append(Connection("R1", 0, "q"))
    # Terminal 1 left unconnected on purpose.
    msg = " || ".join(collect_errors(nl))
    assert "R1" in msg and "not connected" in msg.lower()

    # Also reject an out-of-range terminal index (resistor only has 2: 0, 1).
    nl2 = valid_netlist()
    nl2.elements.append(Element("R2", "resistor", {"R": q(50.0, "ohm")}))
    nl2.connections.append(Connection("R2", 0, "q"))
    nl2.connections.append(Connection("R2", 2, "gnd"))
    msg2 = " || ".join(collect_errors(nl2))
    assert "R2" in msg2 and "out of range" in msg2.lower()
