"""Round-trip serialize/deserialize tests: must be lossless."""

from __future__ import annotations

import pytest
from core.netlist import (
    FORMAT,
    SchemaError,
    UnitError,
    dump,
    dumps,
    from_dict,
    load,
    loads,
    to_dict,
)
from helpers import valid_netlist


def test_dict_round_trip_is_lossless():
    nl = valid_netlist()
    assert from_dict(to_dict(nl)) == nl


def test_json_string_round_trip_is_lossless():
    nl = valid_netlist()
    assert loads(dumps(nl)) == nl


def test_file_round_trip_is_lossless(tmp_path):
    nl = valid_netlist()
    path = tmp_path / "net.json"
    dump(nl, path)
    assert load(path) == nl


def test_serialized_dict_has_schema_header():
    d = to_dict(valid_netlist())
    assert d["format"] == FORMAT
    assert d["version"] == "1.0"
    assert isinstance(d["nodes"], list)
    assert isinstance(d["elements"], list)
    assert isinstance(d["connections"], list)


def test_units_survive_round_trip():
    nl = valid_netlist()
    back = loads(dumps(nl))
    j1 = back.element_by_id("J1")
    assert j1 is not None
    assert j1.params["Ic"].unit == "nA"
    assert j1.params["Ic"].value == 30.0


def test_loads_rejects_invalid_json():
    with pytest.raises(SchemaError):
        loads("{not valid json")


def test_from_dict_rejects_wrong_format():
    d = to_dict(valid_netlist())
    d["format"] = "something-else"
    with pytest.raises(SchemaError):
        from_dict(d)


def test_from_dict_rejects_bad_structure():
    with pytest.raises(SchemaError):
        from_dict({"format": FORMAT, "nodes": "not-a-list"})


def test_from_dict_propagates_unknown_unit():
    d = to_dict(valid_netlist())
    d["elements"][0]["params"]["Ic"]["unit"] = "not-a-unit"
    with pytest.raises(UnitError):
        from_dict(d)


def test_dumps_validate_flag_runs_validation():
    nl = valid_netlist()
    # Should not raise for a valid netlist.
    dumps(nl, validate=True)
