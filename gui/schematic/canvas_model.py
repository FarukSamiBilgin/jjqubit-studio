"""Pure-Python schematic canvas model and netlist conversion.

This module has NO PySide6 import. It represents the schematic canvas as
plain dataclasses (elements, nodes, wires -- each with a canvas position) and
converts losslessly to/from :class:`core.netlist.Netlist`. Keeping this layer
free of Qt lets the netlist-building logic be unit-tested without a running
event loop or ``QApplication``; the graphics layer (``scene.py``, ``items.py``)
is a thin mirror of this model.

Canvas state maps onto the netlist contract directly:

    CanvasElement  <-> core.netlist.Element    (+ an (x, y) canvas position)
    CanvasNode     <-> a declared node id      (+ an (x, y) canvas position)
    CanvasWire     <-> core.netlist.Connection (element id, terminal index, node id)

The netlist JSON schema carries no layout information, so round-tripping
canvas -> netlist -> canvas does not preserve pixel positions -- only nodes,
elements, params and wiring are guaranteed to survive. That is the full
extent of what a lossless round trip means for this module.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from core.netlist import (
    ELEMENT_TYPES,
    SCHEMA_VERSION,
    Connection,
    Element,
    Netlist,
    Quantity,
    collect_errors,
)

# Short id prefixes used when auto-generating element ids for the palette.
# Purely cosmetic (any unique string id is legal in the netlist contract).
_ID_PREFIXES: dict[str, str] = {
    "junction": "J",
    "capacitor": "C",
    "inductor": "L",
    "resistor": "R",
    "resonator": "RES",
    "transmission_line": "TL",
    "current_source": "I",
    "ground": "GND",
}

# Auto-layout geometry for netlists loaded without any position information.
_GRID_SPACING_X = 160.0
_GRID_SPACING_Y = 120.0
_GRID_COLUMNS = 4


@dataclass
class CanvasElement:
    """One circuit element placed on the canvas.

    Args:
        id: Unique element id (matches ``core.netlist.Element.id``).
        type: Element type key, one of the keys of ``core.netlist.ELEMENT_TYPES``.
        params: Parameter name -> :class:`core.netlist.Quantity`, values kept in
            whatever unit the user entered (not necessarily SI).
        x: Canvas x position (scene coordinates) of the element's anchor point.
        y: Canvas y position (scene coordinates).
    """

    id: str
    type: str
    params: dict[str, Quantity] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0


@dataclass
class CanvasNode:
    """One electrical node marker placed on the canvas.

    Args:
        id: Node id (matches an entry in ``core.netlist.Netlist.nodes``).
        x: Canvas x position.
        y: Canvas y position.
    """

    id: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class CanvasWire:
    """One terminal-to-node binding; mirrors ``core.netlist.Connection``.

    Args:
        element_id: The id of the element being wired.
        terminal: 0-based index into that element type's terminal tuple.
        node_id: The node this terminal is tied to.
    """

    element_id: str
    terminal: int
    node_id: str


@dataclass
class CanvasModel:
    """The full schematic canvas state: elements, nodes and their wiring.

    This is the single source of truth that the graphics layer (scene/items)
    mirrors into ``QGraphicsItem``s, and the source data for building a
    :class:`core.netlist.Netlist`. It intentionally mirrors the netlist
    contract's three collections (elements, nodes, connections) so
    :meth:`to_netlist` and :func:`from_netlist` are direct, lossless
    conversions on circuit topology.

    Args:
        name: Human-readable circuit name, becomes ``Netlist.name``.
        elements: Placed elements, keyed by id.
        nodes: Placed nodes, keyed by id.
        wires: Terminal-to-node bindings.
        version: Netlist schema version, preserved across load/save so a
            round trip does not silently rewrite it to the current default.
    """

    name: str = "Untitled circuit"
    elements: dict[str, CanvasElement] = field(default_factory=dict)
    nodes: dict[str, CanvasNode] = field(default_factory=dict)
    wires: list[CanvasWire] = field(default_factory=list)
    version: str = SCHEMA_VERSION

    # -- id generation --------------------------------------------------

    def next_element_id(self, type_name: str) -> str:
        """Return an unused element id for ``type_name`` (e.g. ``"C2"``)."""
        prefix = _ID_PREFIXES.get(type_name, type_name[:2].upper() or "EL")
        for i in itertools.count(1):
            candidate = f"{prefix}{i}"
            if candidate not in self.elements:
                return candidate
        raise AssertionError("unreachable")  # pragma: no cover

    def next_node_id(self) -> str:
        """Return an unused node id (e.g. ``"n3"``)."""
        for i in itertools.count(1):
            candidate = f"n{i}"
            if candidate not in self.nodes:
                return candidate
        raise AssertionError("unreachable")  # pragma: no cover

    # -- mutation: elements -----------------------------------------------

    def add_element(
        self,
        type_name: str,
        x: float = 0.0,
        y: float = 0.0,
        element_id: str | None = None,
    ) -> CanvasElement:
        """Place a new element of ``type_name`` on the canvas.

        Args:
            type_name: Must be a key of ``core.netlist.ELEMENT_TYPES``.
            x: Canvas x position for the new element.
            y: Canvas y position for the new element.
            element_id: Explicit id to use; auto-generated if omitted.

        Raises:
            ValueError: if ``type_name`` is not a registered element type, or
                ``element_id`` is already in use.
        """
        if type_name not in ELEMENT_TYPES:
            known = ", ".join(sorted(ELEMENT_TYPES))
            raise ValueError(f"unknown element type {type_name!r} (known: {known})")
        el_id = element_id or self.next_element_id(type_name)
        if el_id in self.elements:
            raise ValueError(f"duplicate element id {el_id!r}")
        el = CanvasElement(id=el_id, type=type_name, params={}, x=x, y=y)
        self.elements[el_id] = el
        return el

    def remove_element(self, element_id: str) -> None:
        """Remove an element and any wires attached to it."""
        self.elements.pop(element_id, None)
        self.wires = [w for w in self.wires if w.element_id != element_id]

    def set_param(self, element_id: str, name: str, value: Quantity) -> None:
        """Set parameter ``name`` on element ``element_id`` to ``value``.

        Raises:
            KeyError: if ``element_id`` does not exist.
        """
        self.elements[element_id].params[name] = value

    def clear_param(self, element_id: str, name: str) -> None:
        """Remove parameter ``name`` from element ``element_id`` if present."""
        self.elements[element_id].params.pop(name, None)

    # -- mutation: nodes ----------------------------------------------------

    def add_node(
        self, x: float = 0.0, y: float = 0.0, node_id: str | None = None
    ) -> CanvasNode:
        """Place a new node marker on the canvas.

        Raises:
            ValueError: if ``node_id`` is already in use.
        """
        node_id = node_id or self.next_node_id()
        if node_id in self.nodes:
            raise ValueError(f"duplicate node id {node_id!r}")
        node = CanvasNode(id=node_id, x=x, y=y)
        self.nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        """Remove a node and any wires attached to it."""
        self.nodes.pop(node_id, None)
        self.wires = [w for w in self.wires if w.node_id != node_id]

    def rename_node(self, old_id: str, new_id: str) -> None:
        """Rename node ``old_id`` to ``new_id``, updating all its wires.

        Raises:
            KeyError: if ``old_id`` does not exist.
            ValueError: if ``new_id`` is already used by a different node.
        """
        if new_id != old_id and new_id in self.nodes:
            raise ValueError(f"duplicate node id {new_id!r}")
        node = self.nodes.pop(old_id)
        node.id = new_id
        self.nodes[new_id] = node
        for w in self.wires:
            if w.node_id == old_id:
                w.node_id = new_id

    # -- mutation: wiring -----------------------------------------------------

    def connect(self, element_id: str, terminal: int, node_id: str) -> CanvasWire:
        """Bind one element terminal to one node.

        Any prior binding for that terminal is replaced, since a terminal can
        only ever sit on one node (the netlist contract requires each terminal
        to be bound exactly once).

        Raises:
            ValueError: if ``element_id`` or ``node_id`` is unknown, or
                ``terminal`` is out of range for the element's type.
        """
        el = self.elements.get(element_id)
        if el is None:
            raise ValueError(f"unknown element {element_id!r}")
        if node_id not in self.nodes:
            raise ValueError(f"unknown node {node_id!r}")
        etype = ELEMENT_TYPES[el.type]
        if not (0 <= terminal < etype.n_terminals):
            raise ValueError(
                f"terminal {terminal} out of range for {el.type!r} "
                f"(0..{etype.n_terminals - 1})"
            )
        self.disconnect(element_id, terminal)
        wire = CanvasWire(element_id=element_id, terminal=terminal, node_id=node_id)
        self.wires.append(wire)
        return wire

    def disconnect(self, element_id: str, terminal: int) -> None:
        """Remove any wire bound to ``(element_id, terminal)``, if present."""
        self.wires = [
            w
            for w in self.wires
            if not (w.element_id == element_id and w.terminal == terminal)
        ]

    def node_of(self, element_id: str, terminal: int) -> str | None:
        """Return the node id bound to ``(element_id, terminal)``, or ``None``."""
        for w in self.wires:
            if w.element_id == element_id and w.terminal == terminal:
                return w.node_id
        return None

    # -- conversion -----------------------------------------------------------

    def to_netlist(self) -> Netlist:
        """Build a :class:`core.netlist.Netlist` from the current canvas state.

        This performs NO validation; call ``.validate()`` or
        :func:`core.netlist.collect_errors` on the result (or use
        :meth:`collect_errors` below) before handing it to a solver.
        """
        elements = [
            Element(id=el.id, type=el.type, params=dict(el.params))
            for el in self.elements.values()
        ]
        connections = [
            Connection(element=w.element_id, terminal=w.terminal, node=w.node_id)
            for w in self.wires
        ]
        return Netlist(
            name=self.name,
            nodes=list(self.nodes.keys()),
            elements=elements,
            connections=connections,
            version=self.version,
        )

    def collect_errors(self) -> list[str]:
        """Validate the current canvas state via ``core.netlist``.

        Returns:
            A list of human-readable problems (empty if the netlist implied by
            the current canvas is valid). Never raises -- suitable for live
            UI error display. This is a thin pass-through to
            :func:`core.netlist.collect_errors`; no physics or extra semantic
            checks are added here.
        """
        return collect_errors(self.to_netlist())


def from_netlist(netlist: Netlist) -> CanvasModel:
    """Build a :class:`CanvasModel` from a loaded :class:`core.netlist.Netlist`.

    The netlist schema carries no layout, so elements and nodes are placed on
    an auto-generated grid; only topology (nodes, elements, params, wiring) is
    reproduced from the source netlist -- exactly what ``to_netlist`` can turn
    back into an equivalent ``Netlist``.

    Args:
        netlist: The netlist to load onto a fresh canvas.
    """
    model = CanvasModel(name=netlist.name, version=netlist.version)

    for i, node_id in enumerate(netlist.nodes):
        col = i % _GRID_COLUMNS
        row = i // _GRID_COLUMNS
        model.add_node(x=col * _GRID_SPACING_X, y=row * _GRID_SPACING_Y, node_id=node_id)

    node_rows = (len(netlist.nodes) + _GRID_COLUMNS - 1) // _GRID_COLUMNS
    y_offset = (node_rows + 1) * _GRID_SPACING_Y

    for i, el in enumerate(netlist.elements):
        col = i % _GRID_COLUMNS
        row = i // _GRID_COLUMNS
        model.elements[el.id] = CanvasElement(
            id=el.id,
            type=el.type,
            params=dict(el.params),
            x=col * _GRID_SPACING_X,
            y=y_offset + row * _GRID_SPACING_Y,
        )

    for el in netlist.elements:
        for terminal, node_id in enumerate(netlist.nodes_of(el.id)):
            if node_id:
                model.wires.append(
                    CanvasWire(element_id=el.id, terminal=terminal, node_id=node_id)
                )

    return model
