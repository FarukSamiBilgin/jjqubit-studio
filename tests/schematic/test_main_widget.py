"""Tests for the top-level ``SchematicEditor`` widget, the library panel, and
the view's zoom/grid/pan mechanics -- all headless via the ``qapp`` fixture.

Covers the "definition of done" acceptance path end to end at the widget
level: build the widget, load an example netlist file, edit a parameter,
save it back out, and confirm the file round-trips through ``core.netlist``.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from core.netlist import ELEMENT_TYPES, Quantity, load

from gui.schematic.library_panel import LibraryPanel
from gui.schematic.main_widget import SchematicEditor
from gui.schematic.scene import ELEMENT_TYPE_MIME
from gui.schematic.view import MAX_SCALE, MIN_SCALE, SchematicView

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


# -- library panel ----------------------------------------------------------------


def test_library_panel_lists_all_eight_element_types(qapp):
    panel = LibraryPanel()
    assert panel.count() == len(ELEMENT_TYPES)
    listed = set()
    from PySide6.QtCore import Qt

    for i in range(panel.count()):
        listed.add(panel.item(i).data(Qt.UserRole))
    assert listed == set(ELEMENT_TYPES)


# -- view: zoom / grid --------------------------------------------------------------


def test_zoom_in_and_out_changes_scale(qapp):
    view = SchematicView()
    view.zoom_in()
    assert view._scale > 1.0
    view.zoom_reset()
    assert view._scale == 1.0


def test_zoom_is_clamped(qapp):
    view = SchematicView()
    for _ in range(200):
        view.zoom_in()
    assert view._scale <= MAX_SCALE
    view.zoom_reset()
    for _ in range(200):
        view.zoom_out()
    assert view._scale >= MIN_SCALE


def test_grid_toggle(qapp):
    view = SchematicView()
    assert view._grid_visible is True
    view.set_grid_visible(False)
    assert view._grid_visible is False


# -- SchematicEditor: load / edit / save round trip --------------------------------


def test_editor_loads_example_netlist(qapp):
    editor = SchematicEditor()
    editor.load_netlist_file(str(EXAMPLES_DIR / "transmon_readout.json"))
    assert set(editor.scene.element_items) == {
        "J1", "Cs", "Cg", "RES1", "Ck", "TL1", "Rload", "GND1",
    }


def test_editor_load_edit_save_round_trip(qapp, tmp_path):
    editor = SchematicEditor()
    editor.load_netlist_file(str(EXAMPLES_DIR / "rcsj_bias.json"))

    # Selecting an element should populate the property panel.
    el_item = editor.scene.element_items["J1"]
    el_item.setSelected(True)
    assert editor.properties._element_id == "J1"

    # Edit a parameter through the same path the property panel uses.
    editor.scene.model.set_param("J1", "Ic", Quantity(21.0, "nA"))

    out_path = tmp_path / "roundtrip.json"
    editor.save_netlist_file(str(out_path))

    reloaded = load(str(out_path), validate=True)
    assert reloaded.element_by_id("J1").params["Ic"].value == 21.0
    assert reloaded.element_by_id("J1").params["Ic"].unit == "nA"


def test_save_invalid_netlist_without_validation_writes_file(qapp, tmp_path):
    editor = SchematicEditor()
    # A lone, unwired capacitor: invalid (floating terminals, no ground).
    editor.scene.model.add_element("capacitor", element_id="C1")

    out_path = tmp_path / "invalid.json"
    editor.save_netlist_file(str(out_path), validate=False)

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["elements"][0]["id"] == "C1"


def test_save_invalid_netlist_with_validation_raises(qapp, tmp_path):
    from core.netlist import ValidationError

    editor = SchematicEditor()
    editor.scene.model.add_element("capacitor", element_id="C1")

    with pytest.raises(ValidationError):
        editor.save_netlist_file(str(tmp_path / "should_not_exist.json"), validate=True)


class _FakeDropEvent:
    """Minimal stand-in for QGraphicsSceneDragDropEvent.

    ``QGraphicsSceneDragDropEvent.mimeData()`` has no public setter in
    PySide6 (it is populated internally by the real Qt drag machinery), so a
    genuine event can't carry custom mime data in a unit test. ``dropEvent``
    only calls ``mimeData()``, ``scenePos()`` and ``acceptProposedAction()``,
    so a small duck-typed stub exercises the same code path.
    """

    def __init__(self, mime, scene_pos):
        self._mime = mime
        self._scene_pos = scene_pos
        self.accepted = False

    def mimeData(self):
        return self._mime

    def scenePos(self):
        return self._scene_pos

    def acceptProposedAction(self):
        self.accepted = True


def test_drag_drop_mime_type_places_element(qapp):
    from PySide6.QtCore import QMimeData, QPointF

    editor = SchematicEditor()
    mime = QMimeData()
    mime.setData(ELEMENT_TYPE_MIME, b"inductor")

    drop_event = _FakeDropEvent(mime, QPointF(50, 50))
    editor.scene.dropEvent(drop_event)

    assert drop_event.accepted
    types_placed = {el.type for el in editor.scene.model.elements.values()}
    assert "inductor" in types_placed
