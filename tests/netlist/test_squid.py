"""Tests for the `squid` element type (flux-tunable transmon junction).

Added in Faz 1: a two-terminal flux-tunable Josephson element with required
Ic_max/Cj/Rn and optional d (asymmetry) and flux (Phi/Phi0). See
core/solvers/quantum/quantization.py for the physics and
tests/validation/test_tunable_transmon.py for the analytic cross-checks.
"""

from __future__ import annotations

import pytest
from core.netlist import (
    ELEMENT_TYPES,
    Connection,
    Element,
    ValidationError,
    collect_errors,
    dumps,
    loads,
    validate,
)
from helpers import q, valid_netlist


def _with_squid(nl, **params):
    """Attach a squid between 'q' and 'gnd'."""
    nl.elements.append(Element("SQ1", "squid", params))
    nl.connections.append(Connection("SQ1", 0, "q"))
    nl.connections.append(Connection("SQ1", 1, "gnd"))
    return nl


def _full_squid(nl, **overrides):
    params = {
        "Ic_max": q(30.0, "nA"),
        "Cj": q(2.0, "fF"),
        "Rn": q(10.0, "kohm"),
    }
    params.update(overrides)
    return _with_squid(nl, **params)


def test_squid_is_registered_with_two_terminals():
    etype = ELEMENT_TYPES["squid"]
    assert etype.terminals == ("p", "n")
    assert etype.n_terminals == 2


def test_squid_required_and_optional_params():
    etype = ELEMENT_TYPES["squid"]
    assert etype.param("Ic_max").dimension == "current"
    assert etype.param("Ic_max").required is True
    assert etype.param("Cj").dimension == "capacitance"
    assert etype.param("Rn").dimension == "resistance"
    # d and flux are optional and dimensionless.
    assert etype.param("d").required is False
    assert etype.param("d").dimension == "dimensionless"
    assert etype.param("flux").required is False
    assert etype.param("flux").dimension == "dimensionless"


def test_valid_squid_without_optional_params_passes():
    nl = _full_squid(valid_netlist())
    assert collect_errors(nl) == []
    validate(nl)  # must not raise


def test_valid_squid_with_flux_and_asymmetry_passes():
    nl = _full_squid(valid_netlist(), flux=q(0.25, ""), d=q(0.05, ""))
    assert collect_errors(nl) == []
    validate(nl)


def test_squid_round_trips():
    nl = _full_squid(valid_netlist(), flux=q(0.25, ""), d=q(0.05, ""))
    reloaded = loads(dumps(nl))
    assert reloaded == nl
    sq = reloaded.element_by_id("SQ1")
    assert sq.params["Ic_max"].unit == "nA"
    assert sq.params["flux"].value == 0.25
    assert sq.params["d"].value == 0.05


def test_squid_missing_required_ic_max_detected():
    nl = _with_squid(valid_netlist(), Cj=q(2.0, "fF"), Rn=q(10.0, "kohm"))
    msg = " || ".join(collect_errors(nl))
    assert "SQ1" in msg and "Ic_max" in msg and "missing required" in msg.lower()
    with pytest.raises(ValidationError):
        validate(nl)


def test_squid_wrong_dimension_on_ic_max_detected():
    # Classic unit-confusion: Ic_max given in a capacitance unit.
    nl = _full_squid(valid_netlist(), Ic_max=q(30.0, "fF"))
    msg = " || ".join(collect_errors(nl))
    assert "SQ1" in msg and "current" in msg and "capacitance" in msg


def test_squid_unknown_parameter_detected():
    nl = _full_squid(valid_netlist(), bogus=q(1.0, ""))
    msg = " || ".join(collect_errors(nl))
    assert "bogus" in msg and "unknown parameter" in msg.lower()
