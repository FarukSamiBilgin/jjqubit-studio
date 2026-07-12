"""Tests for the QGraphicsScene layer (headless, via the Qt "offscreen" platform).

These exercise the graphics <-> model sync (add/move/delete/wire) that
``canvas_model.py`` alone can't cover, without needing pytest-qt: a shared
``QApplication`` (the ``qapp`` fixture) is enough since we drive the scene
programmatically rather than through real mouse/keyboard input.
"""
from __future__ import annotations

import pathlib

from core.netlist import load

from gui.schematic.items import ElementItem, NodeItem, WireItem
from gui.schematic.scene import SchematicScene

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


def test_scene_starts_empty(qapp):
    scene = SchematicScene()
    assert scene.element_items == {}
    assert scene.node_items == {}
    assert scene.wire_items == []


def test_add_element_and_node_creates_matching_graphics_items(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    item = scene.add_element_at("capacitor", QPointF(40, 40))
    assert isinstance(item, ElementItem)
    assert item.element_id in scene.model.elements
    assert scene.element_items[item.element_id] is item

    node_item = scene.add_node_at(QPointF(100, 100))
    assert isinstance(node_item, NodeItem)
    assert node_item.node_id in scene.model.nodes


def test_terminal_and_node_click_creates_a_wire(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    el_item = scene.add_element_at("resistor", QPointF(0, 0))
    node_item = scene.add_node_at(QPointF(200, 0))

    scene.terminal_clicked(el_item, 0)
    scene.node_clicked(node_item)

    assert scene.model.node_of(el_item.element_id, 0) == node_item.node_id
    assert len(scene.wire_items) == 1
    wire = scene.wire_items[0]
    assert isinstance(wire, WireItem)
    assert wire.element_item is el_item
    assert wire.node_item is node_item


def test_clicking_same_terminal_twice_cancels_pending_wire(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    el_item = scene.add_element_at("resistor", QPointF(0, 0))
    node_item = scene.add_node_at(QPointF(200, 0))

    scene.terminal_clicked(el_item, 0)
    scene.terminal_clicked(el_item, 0)  # cancels
    scene.node_clicked(node_item)  # no pending terminal: no-op

    assert scene.model.node_of(el_item.element_id, 0) is None
    assert scene.wire_items == []


def test_remove_element_item_clears_model_and_wires(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    el_item = scene.add_element_at("resistor", QPointF(0, 0))
    node_item = scene.add_node_at(QPointF(200, 0))
    scene.terminal_clicked(el_item, 0)
    scene.node_clicked(node_item)

    scene.remove_element_item(el_item)
    assert el_item.element_id not in scene.model.elements
    assert scene.wire_items == []
    # The node itself should still exist -- only the element+wire were removed.
    assert node_item.node_id in scene.model.nodes


def test_element_move_updates_model_position_and_wire_endpoints(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    el_item = scene.add_element_at("resistor", QPointF(0, 0))
    node_item = scene.add_node_at(QPointF(200, 0))
    scene.terminal_clicked(el_item, 0)
    scene.node_clicked(node_item)

    el_item.setPos(QPointF(300, 300))
    scene.on_element_moved(el_item)

    model_el = scene.model.elements[el_item.element_id]
    assert (model_el.x, model_el.y) == (300, 300)
    wire = scene.wire_items[0]
    assert wire.line().p1() == el_item.terminal_scene_pos(0)


def test_load_netlist_populates_scene_for_both_examples(qapp):
    for filename in ("transmon_readout.json", "rcsj_bias.json"):
        nl = load(str(EXAMPLES_DIR / filename), validate=True)
        scene = SchematicScene()
        scene.load_netlist(nl)

        assert set(scene.element_items) == {el.id for el in nl.elements}
        assert set(scene.node_items) == set(nl.nodes)
        assert len(scene.wire_items) == len(nl.connections)

        rebuilt = scene.model.to_netlist()
        assert rebuilt == nl


def test_delete_selected_removes_selected_items(qapp):
    from PySide6.QtCore import QPointF

    scene = SchematicScene()
    el_item = scene.add_element_at("resistor", QPointF(0, 0))
    el_item.setSelected(True)

    scene.delete_selected()
    assert el_item.element_id not in scene.model.elements
