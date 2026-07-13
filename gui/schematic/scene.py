"""The schematic ``QGraphicsScene``: ties ``CanvasModel`` to graphics items.

``SchematicScene`` owns one :class:`~gui.schematic.canvas_model.CanvasModel`
and keeps a matching set of :class:`~gui.schematic.items.ElementItem`,
:class:`~gui.schematic.items.NodeItem` and :class:`~gui.schematic.items.WireItem`
objects in sync with it. All netlist-shaped mutations (add/remove
element/node, connect/disconnect terminals) go through the model; this class
is the only place that also touches the graphics side.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneDragDropEvent

from .canvas_model import CanvasModel, from_netlist
from .items import ElementItem, NodeItem, WireItem, snap

ELEMENT_TYPE_MIME = "application/x-jjqubit-element-type"


class SchematicScene(QGraphicsScene):
    """A ``QGraphicsScene`` backed by a :class:`CanvasModel`.

    Signals:
        selection_changed_element: Emitted with the selected ``ElementItem``
            (or ``None`` when nothing/other is selected) so a property panel
            can follow the selection.
        model_changed: Emitted after any mutation, so listeners can refresh
            validation state.
    """

    selection_changed_element = Signal(object)
    model_changed = Signal()

    def __init__(self, model: CanvasModel | None = None) -> None:
        super().__init__()
        self.model = model or CanvasModel()
        self.element_items: dict[str, ElementItem] = {}
        self.node_items: dict[str, NodeItem] = {}
        self.wire_items: list[WireItem] = []
        self._pending_terminal: tuple[ElementItem, int] | None = None
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.selectionChanged.connect(self._on_selection_changed)
        self._rebuild_from_model()

    # -- (re)building the graphics side from the model -----------------------

    def _rebuild_from_model(self) -> None:
        """Recreate every graphics item from the current model state.

        Used after loading a netlist wholesale; incremental edits use the
        targeted add_*/remove_* methods instead.
        """
        self.clear()
        self.element_items.clear()
        self.node_items.clear()
        self.wire_items.clear()
        self._pending_terminal = None

        for node in self.model.nodes.values():
            item = NodeItem(node.id)
            item.setPos(node.x, node.y)
            self.addItem(item)
            self.node_items[node.id] = item

        for el in self.model.elements.values():
            item = ElementItem(el.id, el.type)
            item.setPos(el.x, el.y)
            self.addItem(item)
            self.element_items[el.id] = item

        for wire in self.model.wires:
            el_item = self.element_items.get(wire.element_id)
            node_item = self.node_items.get(wire.node_id)
            if el_item is None or node_item is None:
                continue  # pragma: no cover - defensive, model should be consistent
            wire_item = WireItem(el_item, wire.terminal, node_item)
            self.addItem(wire_item)
            self.wire_items.append(wire_item)

        self.model_changed.emit()

    def load_netlist(self, netlist) -> None:
        """Replace the current canvas with ``netlist`` (a ``core.netlist.Netlist``)."""
        self.model = from_netlist(netlist)
        self._rebuild_from_model()

    # -- element / node placement --------------------------------------------

    def add_element_at(self, type_name: str, pos: QPointF) -> ElementItem:
        """Place a new element of ``type_name`` centered at scene point ``pos``."""
        el = self.model.add_element(type_name, x=snap(pos.x()), y=snap(pos.y()))
        item = ElementItem(el.id, el.type)
        item.setPos(el.x, el.y)
        self.addItem(item)
        self.element_items[el.id] = item
        self.model_changed.emit()
        return item

    def add_node_at(self, pos: QPointF) -> NodeItem:
        """Place a new (unwired) node marker centered at scene point ``pos``."""
        node = self.model.add_node(x=snap(pos.x()), y=snap(pos.y()))
        item = NodeItem(node.id)
        item.setPos(node.x, node.y)
        self.addItem(item)
        self.node_items[node.id] = item
        self.model_changed.emit()
        return item

    # -- wiring gesture: click a terminal, then click a node (or empty canvas) --

    def terminal_clicked(self, element_item: ElementItem, terminal: int) -> None:
        """Handle a click on a terminal handle (see ``TerminalHandle``)."""
        if self._pending_terminal is not None:
            pending_item, pending_terminal = self._pending_terminal
            if pending_item is element_item and pending_terminal == terminal:
                self._pending_terminal = None  # clicked the same terminal: cancel
                return
        self._pending_terminal = (element_item, terminal)

    def node_clicked(self, node_item: NodeItem) -> None:
        """Handle a click on a node marker: complete a pending wire, if any."""
        if self._pending_terminal is None:
            return
        element_item, terminal = self._pending_terminal
        self._connect(element_item, terminal, node_item)
        self._pending_terminal = None

    def mousePressEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: D102
        # A click on empty canvas while a terminal is pending creates a new
        # node at that point and wires the pending terminal to it.
        if self._pending_terminal is not None and event.button() == Qt.LeftButton:
            transform = self.views()[0].transform() if self.views() else QTransform()
            item = self.itemAt(event.scenePos(), transform)
            if item is None:
                element_item, terminal = self._pending_terminal
                node_item = self.add_node_at(event.scenePos())
                self._connect(element_item, terminal, node_item)
                self._pending_terminal = None
                event.accept()
                return
        super().mousePressEvent(event)

    def _connect(
        self, element_item: ElementItem, terminal: int, node_item: NodeItem
    ) -> None:
        self.model.connect(element_item.element_id, terminal, node_item.node_id)
        # Remove any previous wire item for this exact terminal (a terminal can
        # only be bound once), then add the fresh one.
        self.wire_items = [
            w
            for w in self.wire_items
            if not (w.element_item is element_item and w.terminal == terminal)
        ]
        for w in list(self.items()):
            if (
                isinstance(w, WireItem)
                and w.element_item is element_item
                and w.terminal == terminal
            ):
                self.removeItem(w)
        wire_item = WireItem(element_item, terminal, node_item)
        self.addItem(wire_item)
        self.wire_items.append(wire_item)
        self.model_changed.emit()

    # -- removal --------------------------------------------------------------

    def remove_element_item(self, item: ElementItem) -> None:
        """Remove an element (and its wires) from both model and scene."""
        self.model.remove_element(item.element_id)
        for w in [w for w in self.wire_items if w.element_item is item]:
            self.wire_items.remove(w)
            self.removeItem(w)
        self.element_items.pop(item.element_id, None)
        self.removeItem(item)
        self.model_changed.emit()

    def remove_node_item(self, item: NodeItem) -> None:
        """Remove a node (and its wires) from both model and scene."""
        self.model.remove_node(item.node_id)
        for w in [w for w in self.wire_items if w.node_item is item]:
            self.wire_items.remove(w)
            self.removeItem(w)
        self.node_items.pop(item.node_id, None)
        self.removeItem(item)
        self.model_changed.emit()

    def delete_selected(self) -> None:
        """Delete every currently selected element/node (and their wires)."""
        for item in list(self.selectedItems()):
            if isinstance(item, ElementItem):
                self.remove_element_item(item)
            elif isinstance(item, NodeItem):
                self.remove_node_item(item)

    def keyPressEvent(self, event) -> None:  # noqa: D102 - Qt override
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- movement callbacks (wired from ElementItem/NodeItem.itemChange) -------

    def on_element_moved(self, item: ElementItem) -> None:
        """Sync the model position and refresh wires touching ``item``."""
        el = self.model.elements.get(item.element_id)
        if el is not None:
            el.x, el.y = item.pos().x(), item.pos().y()
        for w in self.wire_items:
            if w.element_item is item:
                w.update_line()

    def on_node_moved(self, item: NodeItem) -> None:
        """Sync the model position and refresh wires touching ``item``."""
        node = self.model.nodes.get(item.node_id)
        if node is not None:
            node.x, node.y = item.pos().x(), item.pos().y()
        for w in self.wire_items:
            if w.node_item is item:
                w.update_line()

    # -- drag and drop from the element library --------------------------------

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: D102
        if event.mimeData().hasFormat(ELEMENT_TYPE_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: D102
        if event.mimeData().hasFormat(ELEMENT_TYPE_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QGraphicsSceneDragDropEvent) -> None:  # noqa: D102
        mime = event.mimeData()
        if mime.hasFormat(ELEMENT_TYPE_MIME):
            type_name = bytes(mime.data(ELEMENT_TYPE_MIME)).decode("utf-8")
            self.add_element_at(type_name, event.scenePos())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # -- selection ------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        selected = self.selectedItems()
        element = (
            selected[0]
            if len(selected) == 1 and isinstance(selected[0], ElementItem)
            else None
        )
        self.selection_changed_element.emit(element)
