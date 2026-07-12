"""Tests for the property/parameter editor panel (headless via ``qapp``).

Verifies the form is generated purely from ``ELEMENT_TYPES[type].params`` --
one field pair per parameter, unit choices restricted to the parameter's
declared dimension -- for every one of the 8 MVP element types, and that
edits are written back into the canvas model with the correct dimension.
"""
from __future__ import annotations

import pytest

from core.netlist import ELEMENT_TYPES, unit_dimension

from gui.schematic.canvas_model import CanvasModel
from gui.schematic.property_panel import PropertyPanel


@pytest.mark.parametrize("type_name", list(ELEMENT_TYPES))
def test_form_has_one_row_per_param_for_every_element_type(qapp, type_name):
    model = CanvasModel()
    el = model.add_element(type_name)
    panel = PropertyPanel(model)

    panel.show_element(el.id)

    etype = ELEMENT_TYPES[type_name]
    assert set(panel._value_boxes) == {p.name for p in etype.params}
    assert set(panel._unit_boxes) == {p.name for p in etype.params}


@pytest.mark.parametrize("type_name", list(ELEMENT_TYPES))
def test_unit_combo_only_offers_units_of_the_right_dimension(qapp, type_name):
    model = CanvasModel()
    el = model.add_element(type_name)
    panel = PropertyPanel(model)
    panel.show_element(el.id)

    etype = ELEMENT_TYPES[type_name]
    for spec in etype.params:
        combo = panel._unit_boxes[spec.name]
        offered = [combo.itemText(i) for i in range(combo.count())]
        assert offered, f"{type_name}.{spec.name} has no offered units"
        for unit in offered:
            assert unit_dimension(unit) == spec.dimension


def test_editing_value_and_unit_writes_back_to_model(qapp):
    model = CanvasModel()
    el = model.add_element("junction")
    panel = PropertyPanel(model)
    panel.show_element(el.id)

    panel._value_boxes["Ic"].setValue(42.0)
    panel._unit_boxes["Ic"].setCurrentText("uA")

    stored = model.elements[el.id].params["Ic"]
    assert stored.value == 42.0
    assert stored.unit == "uA"


def test_clear_resets_to_no_selection_state(qapp):
    model = CanvasModel()
    el = model.add_element("capacitor")
    panel = PropertyPanel(model)
    panel.show_element(el.id)
    assert panel._value_boxes  # populated

    panel.clear()
    assert panel._value_boxes == {}
    assert panel._title.text() == "No element selected"


def test_ground_has_no_params_shows_placeholder_row(qapp):
    model = CanvasModel()
    el = model.add_element("ground")
    panel = PropertyPanel(model)
    panel.show_element(el.id)

    assert panel._value_boxes == {}
    assert panel._form.rowCount() == 1  # the "(no parameters)" placeholder
