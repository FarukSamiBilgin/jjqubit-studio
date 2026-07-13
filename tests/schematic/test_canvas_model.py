"""Unit tests for the pure-Python canvas model (no Qt event loop needed).

Covers: element/node/wire mutation, id generation, the element library
driving off ``core.netlist.ELEMENT_TYPES``, dimension-respecting parameter
edits, canvas -> netlist conversion, and the netlist -> canvas -> netlist
round trip against both example netlists.
"""

from __future__ import annotations

import pathlib

import pytest
from core.netlist import ELEMENT_TYPES, Quantity, load
from gui.schematic.canvas_model import CanvasModel, from_netlist
from gui.schematic.units_ui import default_unit_for, units_for_dimension

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


# -- element library reflects the frozen registry --------------------------------


def test_all_eight_element_types_are_placeable():
    model = CanvasModel()
    for type_name in ELEMENT_TYPES:
        el = model.add_element(type_name)
        assert el.type == type_name
    assert len(model.elements) == 8


def test_unknown_element_type_rejected():
    model = CanvasModel()
    with pytest.raises(ValueError, match="unknown element type"):
        model.add_element("capacitor_bank")


# -- id generation ------------------------------------------------------------


def test_next_element_id_is_unique_and_type_prefixed():
    model = CanvasModel()
    j1 = model.add_element("junction")
    j2 = model.add_element("junction")
    assert j1.id != j2.id
    assert j1.id.startswith("J")
    assert j2.id.startswith("J")


def test_duplicate_element_id_rejected():
    model = CanvasModel()
    model.add_element("capacitor", element_id="C1")
    with pytest.raises(ValueError, match="duplicate element id"):
        model.add_element("capacitor", element_id="C1")


def test_duplicate_node_id_rejected():
    model = CanvasModel()
    model.add_node(node_id="gnd")
    with pytest.raises(ValueError, match="duplicate node id"):
        model.add_node(node_id="gnd")


# -- wiring ---------------------------------------------------------------------


def test_connect_and_disconnect_terminal():
    model = CanvasModel()
    cap = model.add_element("capacitor")
    n1 = model.add_node(node_id="n1")
    n2 = model.add_node(node_id="n2")

    model.connect(cap.id, 0, n1.id)
    model.connect(cap.id, 1, n2.id)
    assert model.node_of(cap.id, 0) == "n1"
    assert model.node_of(cap.id, 1) == "n2"
    assert len(model.wires) == 2

    # Rewiring a terminal replaces the old binding, it doesn't add a second one.
    model.connect(cap.id, 0, n2.id)
    assert model.node_of(cap.id, 0) == "n2"
    assert len(model.wires) == 2

    model.disconnect(cap.id, 1)
    assert model.node_of(cap.id, 1) is None
    assert len(model.wires) == 1


def test_connect_rejects_out_of_range_terminal():
    model = CanvasModel()
    gnd = model.add_element("ground")  # single terminal: index 0 only
    node = model.add_node(node_id="gnd")
    with pytest.raises(ValueError, match="terminal 1 out of range"):
        model.connect(gnd.id, 1, node.id)


def test_connect_rejects_unknown_element_or_node():
    model = CanvasModel()
    node = model.add_node(node_id="n1")
    with pytest.raises(ValueError, match="unknown element"):
        model.connect("ghost", 0, node.id)

    el = model.add_element("resistor")
    with pytest.raises(ValueError, match="unknown node"):
        model.connect(el.id, 0, "ghost-node")


def test_remove_element_drops_its_wires():
    model = CanvasModel()
    cap = model.add_element("capacitor")
    n1 = model.add_node(node_id="n1")
    n2 = model.add_node(node_id="n2")
    model.connect(cap.id, 0, n1.id)
    model.connect(cap.id, 1, n2.id)

    model.remove_element(cap.id)
    assert cap.id not in model.elements
    assert model.wires == []


def test_remove_node_drops_its_wires_but_keeps_element():
    model = CanvasModel()
    cap = model.add_element("capacitor")
    n1 = model.add_node(node_id="n1")
    model.connect(cap.id, 0, n1.id)

    model.remove_node(n1.id)
    assert cap.id in model.elements
    assert model.wires == []


def test_rename_node_updates_wires():
    model = CanvasModel()
    cap = model.add_element("capacitor")
    n1 = model.add_node(node_id="old")
    model.connect(cap.id, 0, n1.id)

    model.rename_node("old", "new")
    assert "old" not in model.nodes
    assert "new" in model.nodes
    assert model.node_of(cap.id, 0) == "new"


# -- parameter editing respects dimensions ---------------------------------------


def test_units_for_dimension_matches_registry_for_every_param():
    """Every ELEMENT_TYPES param dimension must resolve to a non-empty unit
    list, and each unit must genuinely belong to that dimension."""
    from core.netlist import unit_dimension

    for etype in ELEMENT_TYPES.values():
        for spec in etype.params:
            choices = units_for_dimension(spec.dimension)
            assert choices, f"no units for dimension {spec.dimension!r}"
            for u in choices:
                assert unit_dimension(u) == spec.dimension
            assert default_unit_for(spec.dimension) in choices


def test_set_param_stores_quantity_in_native_unit():
    model = CanvasModel()
    el = model.add_element("junction")
    model.set_param(el.id, "Ic", Quantity(30.0, "nA"))
    assert model.elements[el.id].params["Ic"].value == 30.0
    assert model.elements[el.id].params["Ic"].unit == "nA"


# -- canvas -> netlist -------------------------------------------------------------


def test_to_netlist_builds_a_valid_transmon_like_circuit():
    model = CanvasModel(name="mini circuit")
    gnd_node = model.add_node(node_id="gnd")
    q_node = model.add_node(node_id="q")
    j1 = model.add_element("junction", element_id="J1")
    model.set_param(j1.id, "Ic", Quantity(30.0, "nA"))
    model.set_param(j1.id, "Cj", Quantity(2.0, "fF"))
    model.set_param(j1.id, "Rn", Quantity(10.0, "kohm"))
    cap = model.add_element("capacitor", element_id="Cs")
    model.set_param(cap.id, "C", Quantity(70.0, "fF"))
    ground = model.add_element("ground", element_id="GND1")

    model.connect(j1.id, 0, q_node.id)
    model.connect(j1.id, 1, gnd_node.id)
    model.connect(cap.id, 0, q_node.id)
    model.connect(cap.id, 1, gnd_node.id)
    model.connect(ground.id, 0, gnd_node.id)

    errors = model.collect_errors()
    assert errors == []

    nl = model.to_netlist()
    assert nl.name == "mini circuit"
    assert set(nl.nodes) == {"gnd", "q"}
    assert nl.nodes_of("J1") == ["q", "gnd"]


def test_collect_errors_surfaces_missing_ground_without_reimplementing_it():
    """We must not reimplement validation -- just call through to core.netlist."""
    model = CanvasModel()
    n1 = model.add_node(node_id="n1")
    n2 = model.add_node(node_id="n2")
    cap = model.add_element("capacitor")
    model.connect(cap.id, 0, n1.id)
    model.connect(cap.id, 1, n2.id)

    errors = model.collect_errors()
    assert any("ground" in e for e in errors)


# -- netlist -> canvas -> netlist round trip (definition of done) ---------------


@pytest.mark.parametrize("filename", ["transmon_readout.json", "rcsj_bias.json"])
def test_load_then_export_round_trips_losslessly(filename):
    original = load(str(EXAMPLES_DIR / filename), validate=True)

    model = from_netlist(original)
    rebuilt = model.to_netlist()

    assert rebuilt == original


@pytest.mark.parametrize("filename", ["transmon_readout.json", "rcsj_bias.json"])
def test_round_tripped_netlist_still_validates(filename):
    original = load(str(EXAMPLES_DIR / filename), validate=True)
    model = from_netlist(original)
    # Must not raise.
    model.to_netlist().validate()


def test_from_netlist_covers_all_eight_element_types_between_the_two_examples():
    seen: set[str] = set()
    for filename in ("transmon_readout.json", "rcsj_bias.json"):
        nl = load(str(EXAMPLES_DIR / filename), validate=True)
        model = from_netlist(nl)
        seen.update(el.type for el in model.elements.values())
    assert seen == set(ELEMENT_TYPES)
