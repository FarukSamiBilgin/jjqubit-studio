"""Tests for the Quantity type and unit registry."""

from __future__ import annotations

import dataclasses
import math

import pytest
from core.netlist import (
    Quantity,
    SchemaError,
    UnitError,
    is_known_unit,
    known_units,
    unit_dimension,
)


def test_quantity_stores_value_and_unit():
    qty = Quantity(5.0, "GHz")
    assert qty.value == 5.0
    assert qty.unit == "GHz"
    assert qty.dimension == "frequency"


def test_quantity_coerces_int_to_float():
    qty = Quantity(3, "fF")
    assert isinstance(qty.value, float)
    assert qty.value == 3.0


@pytest.mark.parametrize(
    "value,unit,expected_si",
    [
        (5.0, "GHz", 5e9),
        (2.0, "fF", 2e-15),
        (30.0, "nA", 30e-9),
        (10.0, "kohm", 1e4),
        (6.0, "mm", 6e-3),
        (1.0, "ns", 1e-9),
        (8000.0, "", 8000.0),
    ],
)
def test_to_si_conversion(value, unit, expected_si):
    assert math.isclose(Quantity(value, unit).to_si(), expected_si, rel_tol=1e-12)


def test_dimensionless_aliases_accepted():
    for token in ("", "1", "dimensionless"):
        assert Quantity(1.0, token).dimension == "dimensionless"


def test_unknown_unit_raises_unit_error():
    with pytest.raises(UnitError):
        Quantity(1.0, "GHZ")  # wrong case is not registered
    with pytest.raises(UnitError):
        Quantity(1.0, "farad")


def test_unit_dimension_helper():
    assert unit_dimension("nA") == "current"
    assert is_known_unit("fF")
    assert not is_known_unit("bogus")
    with pytest.raises(UnitError):
        unit_dimension("bogus")


def test_known_units_contains_domain_units():
    units = set(known_units())
    for u in ("GHz", "fF", "nA", "ohm", "nH", "mm", "ns"):
        assert u in units


def test_quantity_dict_round_trip():
    qty = Quantity(7.2, "GHz")
    assert Quantity.from_dict(qty.to_dict()) == qty


def test_quantity_from_dict_rejects_bad_structure():
    with pytest.raises(SchemaError):
        Quantity.from_dict({"value": 1.0})  # missing unit
    with pytest.raises(SchemaError):
        Quantity.from_dict({"value": "x", "unit": "GHz"})  # non-numeric value
    with pytest.raises(SchemaError):
        Quantity.from_dict(5.0)  # not a mapping


def test_quantity_is_immutable():
    qty = Quantity(1.0, "GHz")
    with pytest.raises(dataclasses.FrozenInstanceError):
        qty.value = 2.0  # frozen dataclass
